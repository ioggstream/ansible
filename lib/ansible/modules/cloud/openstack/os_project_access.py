#!/usr/bin/python

# Copyright (c) 2015 Hewlett-Packard Development Company, L.P.
#
# This module is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software.  If not, see <http://www.gnu.org/licenses/>.

import logging
logging.basicConfig(level=logging.DEBUG, filename="/tmp/ansible.log")
log = logging.getLogger(__name__)

try:
    import shade
    HAS_SHADE = True
except ImportError:
    HAS_SHADE = False

ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '1.0'}

DOCUMENTATION = '''
---
module: os_project_access
short_description: Manage OpenStack compute flavors acceess
extends_documentation_fragment: openstack
version_added: "2.0"
author: "Roberto Polli (@ioggstream)"
description:
   - Add or remove flavor access from OpenStack.
options:
   state:
     description:
        - Indicate desired state of the resource. When I(state) is 'present',
          ....
     choices: ['present', 'absent']
     required: false
     default: present
   target_project_id:
     description:
        - Project id.
     required: true
   resource_type:
     description:
        - The resource type (eg. nova_flavor, cinder_volume_type)
   resource_name:
     description:
        - The resource name (eg. tiny)
requirements: ["shade"]
'''

EXAMPLES = '''
- name: "Enable access to tiny flavor to your tenant."
  os_project_Access:
    cloud: mycloud
    state: present
    target_project_id: f0f1f2f3f4f5f67f8f9e0e1
    resource_name: tiny
    resource_type: nova_flavor


- name: "Disable access to the given flavor to project"
  os_project_Access:
    cloud: mycloud
    state: absent
    target_project_id: f0f1f2f3f4f5f67f8f9e0e1
    resource_name: tiny
    resource_type: nova_flavor
'''

RETURN = '''
flavor:
    description: Dictionary describing the flavor.
    returned: On success when I(state) is 'present'
    type: dictionary
    contains:
        id:
            description: Flavor ID.
            returned: success
            type: string
            sample: "515256b8-7027-4d73-aa54-4e30a4a4a339"
        name:
            description: Flavor name.
            returned: success
            type: string
            sample: "tiny"

'''


def _get_allowed_projects(cloud, flavor_id):
    return [x.tenant_id
            for x
            in cloud.nova_client.flavor_access.list(flavor=flavor_id)
            ]


def main():
    argument_spec = openstack_full_argument_spec(
        state        = dict(required=False, default='present',
                            choices=['absent', 'present']),

        # required when state is 'present'
        target_project_id          = dict(required=True, type='str'),
        resource_type        = dict(required=True, type='str'),
        resource_name         = dict(required=True, type='str'),
    )

    module_kwargs = openstack_module_kwargs()
    module = AnsibleModule(
        argument_spec,
        supports_check_mode=True,
        required_if=[
            ('state', 'present', ['target_project_id'])
        ],
        **module_kwargs)

    if not HAS_SHADE:
        module.fail_json(msg='shade is required for this module')

    changed = False
    state = module.params['state']
    resource_name = module.params['resource_name']
    resource_type = module.params['resource_type']
    target_project_id = module.params['target_project_id']

    try:
        cloud = shade.operator_cloud(**module.params)

        if resource_type == 'nova_flavor':
            # returns Munch({'NAME_ATTR': 'name', 'tenant_id': u'37e55da59ec842649d84230f3a24eed5',
            # 'HUMAN_ID': False, 'flavor_id': u'6d4d37b9-0480-4a8c-b8c9-f77deaad73f9',
            #  'request_ids': [], 'human_id': None}),
            _get_resource = cloud.get_flavor
            _list_resource_access = cloud.list_flavor_access
            _add_resource_access = cloud.add_flavor_access
            _remove_resource_access = cloud.remove_flavor_access
        elif resource_type == 'cinder_volume_type':
            # returns [Munch({'project_id': u'178cdb9955b047eea7afbe582038dc94',
            #  'properties': {'request_ids': [], 'NAME_ATTR': 'name', 'human_id': None,
            # 'HUMAN_ID': False}, 'id': u'd5573023-b290-42c8-b232-7c5ca493667f'}),
            _get_resource = cloud.get_volume_type
            _list_resource_access = cloud.get_volume_type_access
            _add_resource_access = cloud.add_volume_type_access
            _remove_resource_access = cloud.remove_volume_type_access
        elif resource_type == 'neutron_rbac_policy':
            # Neutron RBAC policies returns:
            #  - target_project instead of project_id
            #  - filters by network_id via the  object_id attribute.
            _get_resource = cloud.get_network
            _list_resource_access = lambda net_id: [
                {'project_id': acl.get('target_project')}
                for acl
                in cloud.list_rbac_policies(filters=dict(object_id=net_id))
            ]
            _add_resource_access = cloud.create_rbac_policy
            _remove_resource_access = cloud.delete_rbac_policy

        else:
            module.exit_json(changed=False,
                             resource_name=resource_name,
                             resource_type=resource_type,
                             error="Not implemented.")

        resource = _get_resource(resource_name)
        if not resource:
            module.exit_json(changed=True,
                             resource_name=resource_name,
                             resource_type=resource_type,
                             error="Not found")
        resource_id = getattr(resource, 'id', resource['id'])
        # _list_resource_access retursn a list of dicts containing 'project_id'
        acls = _list_resource_access(resource_id)
        log.warn("Acls: %r", acls)
        if not all(acl.get('project_id')
                   for acl
                   in acls):
            module.exit_json(changed=False,
                             resource_name=resource_name,
                             resource_type=resource_type,
                             error="Missing project_id in resource output")
        allowed_tenants = [acl['project_id']
                           for acl
                           in acls
                           ]
        if module.check_mode:
            changed_access = any((
                state == 'present' and target_project_id not in allowed_tenants,
                state == 'absent' and target_project_id in allowed_tenants
            ))
            module.exit_json(changed=changed_access)

        if state == 'present':
            if target_project_id not in allowed_tenants:
                _add_resource_access(
                    resource_id, target_project_id
                )
                changed = True
        elif state == 'absent':
            if target_project_id in allowed_tenants:
                _remove_resource_access(
                    resource_id, target_project_id
                )
                changed = True

            module.exit_json(changed=changed,
                             resource=resource,
                             id=resource_id)

        module.exit_json(changed=changed)
    except shade.OpenStackCloudException as e:
        module.fail_json(msg=str(e), **module.params)

    assert False, "Unreachable!"

# this is magic, see lib/ansible/module_common.py
from ansible.module_utils.basic import *
from ansible.module_utils.openstack import *
if __name__ == '__main__':
    main()
