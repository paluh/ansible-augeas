ansible-augeas
==============

Augeas module which exposes simple API for `match`, `set` and `rm` operations. You can execute commands one by one or in chunk.

Requirements:
  - augeas
  - augeas python bindings

Options:
  - `command`
      - required: false
      - choices: [`set`, `rm`, `match`]
      - description: Whether given path should be modified, removed or matched. Command "match" passes results through "result" attribute - every item on this list is an object with "label" and "value" (check second example below). Other commands returns true in case of any modification (so this value is always equal to "changed" attribue - this make more sens in case of bulk execution)
  - `path`:
      - required: false
      -  description: Variable path.
  - `value`:
      - required: false
      - description: Variable value (required for `set` command).
  - `commands`
      - required: false
      - description: Execute many commands at once (some configuration entries have to be created/updated at once - it is impossible to split them across multiple "set" calls). Standard shell quoting is allowed (rember to escape all quotes inside pahts/values - check last example). Expected formats: "set PATH VALUE", "rm PATH" or "match PATH" (look into examples for more details). You can separate commands with any white characters (new lines, spaces etc.). Result is passed through `result` attribute and contains list of tuples: (command, command result).
  - `root`:
      - required: false
      - description: The filesystem root - config files are searched realtively to this path (fallbacks to `AUGEAS_ROOT` which fallbacks to  `/`).
  - `loadpath`:
      - required: false
      - description: Colon-spearated list of directories that modules should be searched in.

Examples:

  - Simple value change

        - name: Force password on sudo group
          action: augeas path=/files/etc/sudoers/spec[user=\"sudo\"]/host_group/command/tag value=PASSWD

  - Results `match` of command - given below action:

        - name: Fetch sshd allowed users
          action: augeas command="match" path="/files/etc/ssh/sshd_config/AllowUsers/*"
          register: ssh_allowed_users

      you can expect value of this shape to be set in `ssh_allowed_users` variable:

        {"changed": false,
         "result": [{"label": "/files/etc/ssh/sshd_config/AllowUsers/1",
                     "value": "paluh"},
                    {"label": "/files/etc/ssh/sshd_config/AllowUsers/2",
                     "value": "foo"},
                    {"label": "/files/etc/ssh/sshd_config/AllowUsers/3",
                     "value": "bar"}]}

  - Quite complex modification - fetch values lists and append new value only if it doesn't exists already in config

        - name: Check whether given user is listed in sshd_config
          action: augeas command='match' path="/files/etc/ssh/sshd_config/AllowUsers/*[.=\"{{ user }}\"]"
          register: user_entry
        - name: Allow user to login through ssh
          action: augeas command="set" path="/files/etc/ssh/sshd_config/AllowUsers/01" value="{{ user }}"
          when: "user_entry.result|length == 0"

  - Bulk command execution

        - name: Add piggy to /etc/hosts
          action:  augeas commands='set /files/etc/hosts/01/ipaddr 192.168.0.1
                                    set /files/etc/hosts/01/canonical pigiron.example.com
                                    set /files/etc/hosts/01/alias[1] pigiron
                                    set /files/etc/hosts/01/alias[2] piggy'

  - Correct quoting in commands expressions (augeas requires quotes in path matching expressions: iface[.=\"eth0\"])

        - name: Redefine eth0 interface
          action: augeas commands='rm /files/etc/network/interfaces/iface[.=\"eth0\"]
                                   set /files/etc/network/interfaces/iface[last()+1] eth0
                                   set /files/etc/network/interfaces/iface[.=\"eth0\"]/family inet
                                   set /files/etc/network/interfaces/iface[.=\"eth0\"]/method manual
                                   set /files/etc/network/interfaces/iface[.=\"eth0\"]/pre-up "ifconfig $IFACE up"
                                   set /files/etc/network/interfaces/iface[.=\"eth0\"]/pre-down "ifconfig $IFACE down"'

Debugging:

  - If you want to check files which are accessible by augeas on server just run:

        ansible all -u USERNAME -i INVENTORY_FILE -m augeas -a \'command="match" path="/augeas/files//*"

  - In case of any errors during augeas execution of your operations this module will return content of `/augeas//error` and you should be able to find problems related to your actions
