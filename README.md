# openstack-python-vim-driver

This is an Open Baton VIM Driver for OpenStack.


## Configuration
The VIM Driver needs a configuration file. By default the VIM Driver expects the configuration file to be located at _/etc/openbaton/openstack_vim_driver.ini_. If you change the type of the VIM driver from its default value the location will change to _/etc/openbaton/\<type\>_vim_driver.ini_.

You can change the location where to look for the configuration file by passing it with the ```-c``` option while starting the VIM Driver e.g. ```openstack-vim-driver -c /etc/openbaton/alternate_conf_file.ini```.
## Usage

After installing the VIM Driver you can start it with the command ```openstack-vim-driver```