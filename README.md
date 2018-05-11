   <img src="https://raw.githubusercontent.com/openbaton/openbaton.github.io/master/images/openBaton.png" width="250"/>

  Copyright © 2015-2016 [Open Baton](http://openbaton.org).
  Licensed under [Apache v2 License](http://www.apache.org/licenses/LICENSE-2.0).

# An Open Baton VIM Driver for OpenStack

This is an Open Baton VIM Driver for OpenStack written in Python.
Unlike the Java versions of VIM Drivers the Python version is not started by the NFVO with a plugin mechanism but has to be started separately.

## Requirements

* Python 3.5 or higher

## Installation
 ```bash
 pip install openstack-vim-driver
 ```

## Configuration
The VIM Driver requires a configuration file in the INI format.
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


## Issue tracker

Issues and bug reports should be posted to the GitHub Issue Tracker of this project

# What is Open Baton?

OpenBaton is an open source project providing a comprehensive implementation of the ETSI Management and Orchestration (MANO) specification.

Open Baton is a ETSI NFV MANO compliant framework. Open Baton was part of the OpenSDNCore (www.opensdncore.org) project started almost three years ago by Fraunhofer FOKUS with the objective of providing a compliant implementation of the ETSI NFV specification.

Open Baton is easily extensible. It integrates with OpenStack, and provides a plugin mechanism for supporting additional VIM types. It supports Network Service management either using a generic VNFM or interoperating with VNF-specific VNFM. It uses different mechanisms (REST or PUB/SUB) for interoperating with the VNFMs. It integrates with additional components for the runtime management of a Network Service. For instance, it provides autoscaling and fault management based on monitoring information coming from the the monitoring system available at the NFVI level.

## Source Code and documentation

The Source Code of the other Open Baton projects can be found [here][openbaton-github] and the documentation can be found [here][openbaton-doc] .

## News and Website

Check the [Open Baton Website][openbaton]
Follow us on Twitter @[openbaton][openbaton-twitter].

## Licensing and distribution
Copyright [2015-2016] Open Baton project

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## Support
The Open Baton project provides community support through the Open Baton Public Mailing List and through StackOverflow using the tags openbaton.

## Supported by
  <img src="https://raw.githubusercontent.com/openbaton/openbaton.github.io/master/images/fokus.png" width="250"/><img src="https://raw.githubusercontent.com/openbaton/openbaton.github.io/master/images/tu.png" width="150"/>

[fokus-logo]: https://raw.githubusercontent.com/openbaton/openbaton.github.io/master/images/fokus.png
[openbaton]: http://openbaton.org
[openbaton-doc]: http://openbaton.org/documentation
[openbaton-github]: http://github.org/openbaton
[openbaton-logo]: https://raw.githubusercontent.com/openbaton/openbaton.github.io/master/images/openBaton.png
[openbaton-mail]: mailto:users@openbaton.org
[openbaton-twitter]: https://twitter.com/openbaton
[tub-logo]: https://raw.githubusercontent.com/openbaton/openbaton.github.io/master/images/tu.png
[openstack-python-vim-driver]: https://github.com/openbaton/openstack-python-vim-driver