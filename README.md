# An Open Baton VIM Driver for OpenStack

This is an Open Baton VIM Driver for OpenStack written in Python.
Unlike the Java versions of VIM Drivers the Python version is not started by the NFVO with a plugin mechanism but has to be started separately.



## Configuration
The VIM Driver needs a configuration file.
By default the VIM Driver expects the configuration file to be located at _/etc/openbaton/openstack_vim_driver.ini_.
If you change the type of the VIM Driver from its default value the location will change to */etc/openbaton/\<type\>_vim_driver.ini*.

You can change the location where to look for the configuration file by passing it with the ```-c``` option while starting the VIM Driver e.g. ```openstack-vim-driver -c /etc/openbaton/alternate_conf_file.ini```.

You can find an example of what to include in the configuration file by calling the VIM Driver with the help option ```openstack-vim-driver --help```.
## Usage

After installing the VIM Driver and creating the configuration file you can start it with the command ```openstack-vim-driver```.
You can pass several options to the ```openstack-vim-driver``` command:

* **-h or --help** shows a help message
* **-t \<TYPE\> or --type \<TYPE\>** lets you specify the type of the VIM Driver (default is openstack)
* **-w \<INT\>** specifies the maximum number of threads for processing requests (default is 100); 0 or negative values are interpreted as infinite
* **-l \<INT\>** specifies the number of threads consuming messages from RabbitMQ (default is 1)
* **-r \<INT\>** specifies the number of threads for sending replies to the NFVO (default is 1)
* **-n \<NAME\> or --name \<NAME\>** lets you specify the name of the VIM Driver; the default is the VIM Driver's type
* **-c \<CONF_FILE\> or --conf-file \<CONF_FILE\>** specifies the location of the configuration file (default is /etc/openbaton/\<type\>_vim_driver.ini)
