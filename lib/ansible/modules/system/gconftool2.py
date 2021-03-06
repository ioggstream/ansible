#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) 2016, Kenneth D. Evensen <kevensen@redhat.com>
#
# This file is part of Ansible (sort of)
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
from ansible.module_utils.basic import AnsibleModule, BOOLEANS_TRUE
from ansible.module_utils.pycompat24 import get_exception
import subprocess

DOCUMENTATION = """
module: gconftool2
author:
    - "Kenneth D. Evensen (@kevensen)"
short_description: Edit GNOME Configurations
description:
  - This module allows for the manipulation of GNOME 2 Configuration via
    gconftool-2.  Please see the gconftool-2(1) man pages for more details.
version_added: "2.3"
options:
  key:
    required: true
    description:
    - A GConf preference key is an element in the GConf repository
      that corresponds to an application preference. See man gconftool-2(1)
  value:
    required: false
    description:
    - Preference keys typically have simple values such as strings,
      integers, or lists of strings and integers. This is ignored if the state
      is "get". See man gconftool-2(1)
  value_type:
    required: false
    choices:
    - int
    - bool
    - float
    - string
    description:
    - The type of value being set. This is ignored if the state is "get".
  state:
    required: true
    choices:
    - get
    - present
    - absent
    description:
    - The action to take upon the key/value.
  config_source:
    required: false
    description:
    - Specify a configuration source to use rather than the default path.
      See man gconftool-2(1)
  direct:
    required: false
    choices: [ "yes", "no" ]
    default: no
    description:
    - Access the config database directly, bypassing server.  If direct is
      specified then the config_source must be specified as well.
      See man gconftool-2(1)

"""

EXAMPLES = """
- name: Change the widget font to "Serif 12"
  gconftool2:
    key: "/desktop/gnome/interface/font_name"
    value_type: "string"
    value: "Serif 12"
"""

RETURN = '''
  key:
    description: The key specified in the module parameters
    returned: success
    type: string
    sample: "/desktop/gnome/interface/font_name"
  value_type:
    description: The type of the value that was changed
    returned: success
    type: string
    sample: "string"
  value:
    description: The value of the preference key after executing the module
    returned: success
    type: string
    sample: "Serif 12"
...
'''


class GConf2Preference(object):
    def __init__(self, ansible, key, value_type, value,
                 direct=False, config_source=""):
        self.ansible = ansible
        self.key = key
        self.value_type = value_type
        self.value = value
        self.config_source = config_source
        self.direct = direct

    def value_already_set(self):
        return False

    def call(self, call_type):
        config_source = ''
        direct = ''
        changed = False
        out = ''

        # If the configuration source is different from the default, create
        # the argument
        if self.config_source is not None and len(self.config_source) > 0:
            config_source = "--config-source " + self.config_source

        # If direct is true, create the argument
        if self.direct:
            direct = "--direct"

        # Execute the call
        try:
            # If the call is "get", then we don't need as many parameters and
            # we can ignore some
            if call_type == 'get':
                process = subprocess.Popen(["gconftool-2 --get " + self.key],
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, shell=True)
            # Otherwise, we will use all relevant parameters
            else:
                process = subprocess.Popen(["gconftool-2 " + direct + " " +
                                           config_source + " --type " +
                                           self.value_type + " --" +
                                           call_type + " " + self.key + " " +
                                           self.value], stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, shell=True)
            # In either case, we will capture the output
            out = process.stdout.read()
            err = process.stderr.read()

            if len(err) > 0:
                self.ansible.fail_json(msg='gconftool-2 failed with error: %s'
                                       % (str(err)))
            else:
                changed = True

        except OSError:
            self.ansible.fail_json(msg='gconftool-2 failed with and exception')

        return changed, out.rstrip()


def main():
    # Setup the Ansible module
    module = AnsibleModule(
        argument_spec=dict(
                           key=dict(required=True, default=None, type='str'),
                           value_type=dict(required=False,
                                           choices=['int', 'bool',
                                                    'float', 'string'],
                                           type='str'),
                           value=dict(required=False, default=None,
                                      type='str'),
                           state=dict(required=True, default=None,
                                      choices=['present', 'get', 'absent'],
                                      type='str'),
                           direct=dict(required=False,
                                       default=False, type='bool'),
                           config_source=dict(required=False,
                                              default=None, type='str')
                           ),
        supports_check_mode=True
    )

    state_values = {"present": "set", "absent": "unset", "get": "get"}

    direct = False
    # Assign module values to dictionary values
    key = module.params['key']
    value_type = module.params['value_type']
    if module.params['value'].lower() == "true":
        value = "true"
    elif module.params['value'] == "false":
        value = "false"
    else:
        value = module.params['value']

    state = state_values[module.params['state']]
    if module.params['direct'] in BOOLEANS_TRUE:
        direct = True
    config_source = module.params['config_source']

    # Initialize some variables for later
    change = False
    new_value = ''

    if state != "get":
        if value is None or value == "":
            module.fail_json(msg='State %s requires "value" to be set'
                             % str(state))
        elif value_type is None or value_type == "":
            module.fail_json(msg='State %s requires "value_type" to be set'
                             % str(state))

        if direct and config_source is None:
            module.fail_json(msg='If "direct" is "yes" then the ' +
                             '"config_source" must be specified')
        elif not direct and config_source is not None:
            module.fail_json(msg='If the "config_source" is specified ' +
                             'then "direct" must be "yes"')

    # Create a gconf2 preference
    gconf_pref = GConf2Preference(module, key, value_type,
                                  value, direct, config_source)
    # Now we get the current value
    _, current_value = gconf_pref.call("get")

    # Check if the current value equals the value we want to set.  If not, make
    # a change
    if current_value != value:
        # If check mode, we know a change would have occured.
        if module.check_mode:
            # So we will set the change to True
            change = True
            # And set the new_value to the value that would have been set
            new_value = value
        # If not check mode make the change.
        else:
            change, new_value = gconf_pref.call(state)
    # If the value we want to set is the same as the current_value, we will
    # set the new_value to the current_value for reporting
    else:
        new_value = current_value

    facts = {}
    facts['gconftool2'] = {'changed': change, 'key': key,
                           'value_type': value_type, 'new_value': new_value,
                           'previous_value': current_value,
                           'playbook_value': module.params['value']}

    module.exit_json(changed=change, ansible_facts=facts)

if __name__ == '__main__':
    main()
