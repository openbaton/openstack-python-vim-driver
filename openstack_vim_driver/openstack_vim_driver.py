import argparse
import configparser
import ipaddress
import time

import sys

import requests
from org.openbaton.plugin.sdk.catalogue import Network, DeploymentFlavour, Subnet, NFVImage, Quota, Server, ImageStatus, \
    AvailabilityZone, PopKeypair
from org.openbaton.plugin.sdk.utils import start_vim_driver, get_map
from org.openbaton.plugin.sdk.vim import VimDriver

import logging
import logging.config
import os.path
import tempfile

from glanceclient import Client as Glance
from neutronclient.v2_0.client import Client as Neutron
from novaclient.client import Client as Nova
import keystoneauth1.loading
import keystoneauth1.session
import keystoneauth1

log = logging.getLogger(__name__)

# used for caching the created pem files
cert_files = {}


def get_keystone_version(authUrl):
    """Probably not even needed."""
    for i in reversed(authUrl.split('/')):
        if i.startswith('v'):
            return i[1:]
    else:
        raise ValueError('Could not extract API version from auth URL')


def create_cert_file(vim_instance):
    """Create a temporary file for storing the SSL certificate of a VIM
    and return the file name. If the cert_files dict already contains
    an entry for the VIM then no new file is created.
    :param vim_instance
    """
    if vim_instance.get('openstackSslCertificate') is not None:
        vim_id = vim_instance.get('id')
        if vim_id in cert_files:
            value = cert_files.get(vim_id)
            # making sure that the certificate was not changed in the vim
            if value.get('cert') == vim_instance.get('openstackSslCertificate'):
                return value.get('file_path')

        cert_file = tempfile.NamedTemporaryFile(delete=False)
        cert_file.write(vim_instance.get('openstackSslCertificate').encode())
        cert_file.flush()
        cert_files[vim_id] = {
            'cert': vim_instance.get('openstackSslCertificate'),
            'file_path': cert_file.name
        }
        return cert_file.name


class OpenstackVimDriver(VimDriver):
    def __init__(self, deallocate_floating_ips=True, connection_timeout=10, wait_for_vm=15):
        self.deallocate_floating_ips = deallocate_floating_ips
        self.connection_timeout = connection_timeout if connection_timeout > 0 else None
        self.wait_for_vm = wait_for_vm

    def get_keystone_session(self, authUrl, username, password, project_id_or_tenant_name, user_domain_name=None,
                             cert_file_path=None):
        loader = keystoneauth1.loading.get_plugin_loader('password')
        cert_file_path = True if cert_file_path is None else cert_file_path
        auth = loader.load_from_options(auth_url=authUrl, username=username, password=password,
                                        project_id=project_id_or_tenant_name, user_domain_name=user_domain_name)
        # theoretically it should be possible to pass a certificate to the session but it seems not to work
        sess = keystoneauth1.session.Session(auth=auth, timeout=self.connection_timeout, verify=cert_file_path)
        return sess

    def get_glance_client(self, vim_instance):
        cert_file_path = create_cert_file(vim_instance)
        glance_client = Glance(version='2',
                               session=self.get_keystone_session(
                                   vim_instance.get('authUrl'),
                                   vim_instance.get('username'),
                                   vim_instance.get('password'),
                                   vim_instance.get('tenant'),
                                   vim_instance.get('domain'),
                                   cert_file_path)
                               )
        return glance_client

    def get_neutron_client(self, vim_instance):
        cert_file_path = create_cert_file(vim_instance)
        neutron_client = Neutron(session=self.get_keystone_session(
            vim_instance.get('authUrl'),
            vim_instance.get('username'),
            vim_instance.get('password'),
            vim_instance.get('tenant'),
            vim_instance.get('domain'),
            cert_file_path))
        return neutron_client

    def get_nova_client(self, vim_instance):
        cert_file_path = create_cert_file(vim_instance)
        nova_client = Nova(version='2',
                           session=self.get_keystone_session(
                               vim_instance.get('authUrl'),
                               vim_instance.get('username'),
                               vim_instance.get('password'),
                               vim_instance.get('tenant'),
                               vim_instance.get('domain'),
                               cert_file_path))
        return nova_client

    def list_images(self, vim_instance: dict, glance_client=None):
        if glance_client is None:
            glance_client = self.get_glance_client(vim_instance)
        return [NFVImage(name=i.get('name'),
                         ext_id=i.get('id'),
                         min_ram=int(i.get('min_ram')),
                         min_disk_space=int(i.get('min_disk')),
                         created=i.get('created_at'),
                         updated=i.get('updated_at'),
                         is_public=True if i.get('visibility') == 'public' else False,
                         disk_format=i.get('disk_format'),
                         container_format=i.get('container_format'),
                         status=ImageStatus(i.get('status').upper())) for i in glance_client.images.list()]

    def add_image(self, vim_instance: dict, image: dict, image_file_or_url, glance_client=None) -> NFVImage:
        """
        Add an image to OpenStack. The method expects the a URL pointing to the image file.

        :param vim_instance:
        :param image: a dictionary containing the keys: name, containerFormat, isPublic, diskFormat, minDiskSpace and minRam
        :param image_file_or_url: the URL pointing to the image file
        :param glance_client:
        :return: an NFVImage object representing the created image
        """
        image_name = image.get('name')
        if image_name is None or image_name == '':
            raise ValueError('The image name to be used for creating the image must be set')
        container_format = image.get('containerFormat')
        if container_format not in ['ami', 'ari', 'aki', 'bare', 'ovf', 'ova', 'docker']:
            raise ValueError(
                'The passed container format is {} but only the following values are allowed: ami, ari, aki, bare, ovf, ova, docker'.format(
                    container_format))
        is_public = image.get('isPublic')
        disk_format = image.get('diskFormat')
        if disk_format not in ['ami', 'ari', 'aki', 'vhd', 'vhdx', 'vmdk', 'raw', 'qcow2', 'vdi', 'iso', 'ploop']:
            raise ValueError(
                'The passed disk format is {} but only the following values are allowed: ami, ari, aki, vhd, vhdx, vmdk, raw, qcow2, vdi, iso, ploop'.format(
                    disk_format))
        min_disk_space = image.get('minDiskSpace')
        if min_disk_space is None or type(min_disk_space) is not int or min_disk_space < 0:
            raise ValueError(
                'The amount of disk space (in GB) required to boot the image has to be set to a non-negative integer value')
        min_ram = image.get('minRam')
        if min_ram is None or type(min_ram) is not int or min_ram < 0:
            raise ValueError(
                'The amount of RAM (in MB) required to boot the image has to be set to a non-negative integer value')
        if glance_client is None:
            glance_client = self.get_glance_client(vim_instance)
        # create image
        try:
            image_created = glance_client.images.create(name=image_name, disk_format=disk_format.lower(),
                                                        container_format=container_format.lower(),
                                                        min_disk=min_disk_space,
                                                        min_ram=min_ram,
                                                        visibility=('public' if is_public else 'private'))
        except Exception as e:
            log.error('Exception while creating the image {}: {}'.format(image_name, e))
            raise
        try:
            with requests.get(image_file_or_url, stream=True) as image_request:
                # upload data to image
                glance_client.images.upload(image_created.id, image_request.raw)
        except Exception as e:
            log.error('Exception while uploading image to VIM {} ({}): {}'.format(vim_instance.get('name'),
                                                                                  vim_instance.get('id'), e))
            try:
                # delete image if upload of data failed
                glance_client.images.delete(image_created.id)
            except:
                log.error('Exception while removing image')
        try:
            image_created = glance_client.images.get(image_created.id)
        except:
            pass
        try:
            image_status = ImageStatus(image_created.status.upper() if
                                       image_created.status is not None and type(image_created.status) == str else None)
        except ValueError:
            log.warning('Image status ' + image_created.status + ' of the created image seems to be invalid')
            image_status = ImageStatus('UNRECOGNIZED')
        return NFVImage(ext_id=image_created.id, name=image_created.name, min_ram=image_created.min_ram,
                        min_disk_space=image_created.min_disk,
                        is_public=(True if image_created.visibility == 'public' else False),
                        disk_format=image_created.disk_format,
                        container_format=image_created.container_format, created=image_created.created_at,
                        updated=image_created.updated_at, status=image_status)

    def __get_subnet(self, subnet_id, neutron_client=None, vim_instance=None):
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        subnets = neutron_client.list_subnets(id=subnet_id).get('subnets')
        if len(subnets) == 0:
            return None
        subnet = subnets[0]
        return Subnet(name=subnet.get('name'), ext_id=subnet.get('id'),
                      network_id=subnet.get('network_id'), cidr=subnet.get('cidr'), gateway_ip=subnet.get('gateway_ip'))

    def __list_subnets(self, neutron_client=None, vim_instance=None):
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        return [Subnet(name=subnet.get('name'), ext_id=subnet.get('id'),
                       network_id=subnet.get('network_id'), cidr=subnet.get('cidr'),
                       gateway_ip=subnet.get('gateway_ip'))
                for subnet in neutron_client.list_subnets().get('subnets')]

    def __list_network_dicts(self, vim_instance: dict, neutron_client=None):
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        return neutron_client.list_networks().get('networks')

    def __list_routers(self, vim_instance, neutron_client=None):
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        routers = neutron_client.list_routers().get('routers')
        return routers

    def __list_ports(self, vim_instance, neutron_client=None):
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        ports = neutron_client.list_ports().get('ports')
        return ports

    def list_networks(self, vim_instance: dict, neutron_client=None):
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        subnets = self.__list_subnets(neutron_client)
        return [Network(name=n.get('name'),
                        ext_id=n.get('id'),
                        external=n.get('router:external'),
                        subnets=list(filter(lambda sn: sn.extId in n.get('subnets'), subnets))) for n in
                neutron_client.list_networks().get('networks')]

    def list_flavors(self, vim_instance: dict, nova_client=None):
        if nova_client is None:
            nova_client = self.get_nova_client(vim_instance)
        flavors = nova_client.flavors.list()
        return [DeploymentFlavour(flavour_key=f.name, ext_id=f.id, ram=f.ram,
                                  disk=f.disk, vcpu=f.vcpus) for f in flavors]

    def list_availability_zones(self, vim_instance: dict, nova_client=None):
        if nova_client is None:
            nova_client = self.get_nova_client(vim_instance)
        zones = nova_client.availability_zones.list()
        # TODO hosts seems not to be used and therefore the empty dict is passed for now.
        # It is populated in the openstack4j version of the vim driver but there it seems to be done incorrectly.
        return [AvailabilityZone(name=z.zoneName, available=z.zoneState.get('available'), hosts={}) for z in zones]

    def list_keys(self, vim_instance: dict, nova_client=None):
        if nova_client is None:
            nova_client = self.get_nova_client(vim_instance)
        keys = nova_client.keypairs.list()
        return [PopKeypair(name=k.name, public_key=k.public_key, fingerprint=k.fingerprint) for k in keys]

    def refresh(self, vim_instance):
        # TODO parallel execution?
        nova_client = self.get_nova_client(vim_instance)
        images = self.list_images(vim_instance)
        networks = self.list_networks(vim_instance)
        flavors = self.list_flavors(vim_instance, nova_client)
        zones = self.list_availability_zones(vim_instance, nova_client)
        keys = self.list_keys(vim_instance, nova_client)
        vim_instance['images'] = [i.get_dict() for i in images]
        vim_instance['networks'] = [n.get_dict() for n in networks]
        vim_instance['flavours'] = [f.get_dict() for f in flavors]
        vim_instance['zones'] = [z.get_dict() for z in zones]
        vim_instance['keys'] = [k.get_dict() for k in keys]
        return vim_instance

    def list_security_groups(self, vim_instance: dict, neutron_client=None):
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        security_groups = neutron_client.list_security_groups().get('security_groups')
        return security_groups

    def __os_server_to_ob_server(self, os_server, images, flavors):
        status, extendedStatus = None, None
        if os_server.status is not None:
            if os_server.status == 'ERROR':
                extendedStatus = '[OpenStack] {}: {}'.format('TODO', 'TODO')
            else:
                extendedStatus = os_server.status
            status = os_server.status
        ips, floating_ips = {}, {}
        if os_server.addresses is not None:
            for address in os_server.addresses:
                entries = os_server.addresses.get(address)
                addrs, floating_addrs = [], None
                for entry in entries:
                    if entry.get('OS-EXT-IPS:type') == 'fixed':
                        addrs.append(entry.get('addr'))
                    elif entry.get('OS-EXT-IPS:type') == 'floating':
                        floating_addrs = entry.get('addr')
                if len(addrs) > 0:
                    ips[address] = addrs
                if floating_addrs is not None:
                    floating_ips[address] = floating_addrs
        image = None
        if os_server.image is not None:
            for i in images:
                if i.extId == os_server.image.get('id'):
                    image = i
                    break
        flavor = None
        if os_server.flavor is not None:
            for f in flavors:
                if f.extId == os_server.flavor.get('id'):
                    flavor = f
                    break
        server = Server(name=os_server.name, ext_id=os_server.id, created=os_server.created, updated=os_server.updated,
                        hostname=os_server.name, instance_name=os_server._info.get('OS-EXT-SRV-ATTR:instance_name'),
                        status=status, extended_status=extendedStatus, ips=ips, floating_ips=floating_ips,
                        hypervisor_host_name=os_server._info.get('OS-EXT-SRV-ATTR:hypervisor_hostname'),
                        image=image, flavor=flavor)
        return server

    def list_server(self, vim_instance: dict):
        nova_client = self.get_nova_client(vim_instance)
        images = self.list_images(vim_instance)
        flavors = self.list_flavors(vim_instance, nova_client=nova_client)
        ob_servers = []
        os_servers = nova_client.servers.list()
        for os_server in os_servers:
            if os_server.tenant_id == vim_instance.get('tenant'):
                ob_server = self.__os_server_to_ob_server(os_server, images, flavors)
                ob_servers.append(ob_server)
        return ob_servers

    def __create_port(self, port_name, network_id, security_groups, subnet_ids, neutron_client, fixed_ip=None):
        create_port_body = {'port': {'network_id': network_id,
                                     'name': port_name}}
        # find a subnet that fits the fixed IP address if provided
        fitting_subnet_id = None
        if fixed_ip not in (None, ''):
            subnets = self.__list_subnets(neutron_client=neutron_client)
            for subnet_id in subnet_ids:
                for subnet in subnets:
                    if ipaddress.ip_address(fixed_ip) in list(
                            ipaddress.ip_network(subnet.get('cidr')).hosts()):
                        fitting_subnet_id = subnet_id
                        break
                else:
                    raise Exception(
                        'The fixed IP {} is not in the range of any of the subnets associated with the network {}'.format(
                            fixed_ip, network_id))
            create_port_body.get('port')['fixed_ips'] = [{'ip_address': fixed_ip, 'subnet_id': fitting_subnet_id}]

        if len(security_groups) > 0:
            create_port_body['security_groups'] = security_groups

        return neutron_client.create_port(create_port_body)

    def __associate_floating_ip_to_port(self, port, floating_network_id, neutron_client, floating_ip_address):
        """
        Associate a floating IP address to the given port. If the floating_ip_address parameter
        is equal to 'random' or the empty string the first available floating IP will be associated or
        a new one created with a random address.

        :param port:
        :param floating_network_id:
        :param neutron_client:
        :param floating_ip_address:
        :return:
        """
        fips = neutron_client.list_floatingips().get('floatingips')
        # check if the floating IP exists already
        for fip in fips:
            if (fip.get('floating_ip_address') == floating_ip_address or floating_ip_address in (
                    'random', '')) and fip.get(
                'floating_network_id') == floating_network_id:
                if fip.get('status').lower() == 'active':
                    if fip.get('port_id') == port.get('port').get('id'):
                        log.debug('Floating IP {} is already associated to port {}'.format(floating_ip_address,
                                                                                           port.get('port').get(
                                                                                               'id')))
                    else:
                        if floating_ip_address not in ('random', ''):
                            raise Exception('Floating IP {} is already in use'.format(floating_ip_address))
                        continue
                else:
                    # associate the already existing floating IP to the port
                    body = {'floatingip':
                                {'port_id': port.get('port').get('id')}
                            }
                    try:
                        neutron_client.update_floatingip(fip.get('id'), body)
                    except Exception as e:
                        if floating_ip_address not in ('random', ''):
                            raise Exception(
                                'Unable to associate floating IP {} to port {}: {}'.format(floating_ip_address,
                                                                                           port.get('port').get('id'),
                                                                                           e))
                        log.warning(
                            'Not able to associate floating IP {} to port {}: {}'.format(fip.get('floating_ip_address'),
                                                                                         port.get('port').get('id'), e))
                        continue
                break
        else:
            # create a new floating IP address
            body = {'port_id': port.get('port').get('id'),
                    'floating_network_id': floating_network_id}
            if floating_ip_address not in ('random', ''):
                body['floating_ip_address'] = floating_ip_address
            try:
                neutron_client.create_floatingip({'floatingip': body})
            except Exception as e:
                raise Exception('Unable to create floating IP address {}: {}'.format(floating_ip_address, e))

    def __create_server(self,
                        vim_instance: dict,
                        name: str,
                        image_name: str,
                        flavor: str,
                        keypair: str,
                        vnfd_connection_points: [dict],
                        security_groups: [str],
                        user_data: str,
                        nova_client=None,
                        neutron_client=None):
        if nova_client is None:
            nova_client = self.get_nova_client(vim_instance)
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        # [{'virtual_link_reference': 'private', 'floatingIp': 'random', 'interfaceId': 0, 'id': 'ba201de1-d525-4a4b-8e70-c42e7ab7ece8', 'hbVersion': 2, 'shared': False}]

        vnfd_connection_points = sorted(vnfd_connection_points, key=lambda net: net.get('interfaceId'))
        networks = self.__list_network_dicts(vim_instance,
                                             neutron_client=neutron_client)  # TODO maybe use networks from vim instead
        s_groups = [g.get('name') for g in self.list_security_groups(vim_instance)]
        security_groups = [g for g in security_groups if g in s_groups]
        images = self.list_images(vim_instance)
        nics = []
        ports = []
        try:
            for vnfdcp in vnfd_connection_points:
                # find the OpenStack network
                network_id = vnfdcp.get('virtual_link_reference_id')
                if network_id in (None, ''):
                    for available_net in networks:
                        if vnfdcp.get('virtual_link_reference') == available_net.get('name') and (
                                        available_net.get('tenant_id') == vim_instance.get(
                                        'tenant') or available_net.get('shared')):
                            network = available_net
                            network_id = network.get('id')
                            break
                    else:
                        raise Exception('Unable to find network with name {} in tenant with ID {}'.format(
                            vnfdcp.get('virtual_link_reference'),
                            vim_instance.get(
                                'tenant')))
                else:
                    try:
                        network = next(net for net in networks if net.get('id') == network_id)
                    except StopIteration:
                        raise Exception('Unable to find network with ID {} in tenant with ID {}'.format(network_id,
                                                                                                        vim_instance.get(
                                                                                                            'tenant')))

                # create a port
                fixed_ip = vnfdcp.get('fixedIp')
                port = self.__create_port('VNFD-{}'.format(vnfdcp.get('id')), network_id, security_groups,
                                          network.get('subnets'), neutron_client, fixed_ip=fixed_ip)
                ports.append(port)

                # associate a floating IP address to the port if needed
                if vnfdcp.get('floatingIp') is not None:
                    if vnfdcp.get('chosenPool') not in (None, ''):
                        pool_name = vnfdcp.get('chosenPool')
                        for net in vim_instance.get('networks'):
                            if net.get('name') == pool_name:
                                ext_net_id = net.get('extId')
                        else:
                            raise Exception(
                                'Unable to find the network {} that shall be used as a floating IP pool (specified in the connection point\'s chosenPool field)')
                    else:
                        # find the external network
                        ext_net_id = self.__find_connected_external_network(network_id, vim_instance.get('networks'),
                                                                            self.__list_routers(vim_instance,
                                                                                                neutron_client),
                                                                            self.__list_ports(vim_instance,
                                                                                              neutron_client))
                    self.__associate_floating_ip_to_port(port, ext_net_id, neutron_client, vnfdcp.get('floatingIp'))

                nic = {'net-id': network.get('id'), 'port-id': port.get('port').get('id')}
                if fixed_ip not in (None, ''):
                    nic['v4-fixed-ip'] = fixed_ip
                nics.append(nic)

            # find correct image
            for i in images:
                if i.name == image_name or i.extId == image_name:
                    image = i
                    break
            else:
                raise Exception('Not found image {} in VIM instance {}'.format(image_name, vim_instance.get('name')))
            # check image status
            if image.status is None or image.status != ImageStatus.ACTIVE:
                raise Exception(
                    'Image {} ({}) is not yet in active state. Try again later...'.format(image.name, image.extId))
            # find correct flavor ID
            flavors = self.list_flavors(vim_instance, nova_client)
            for f in flavors:
                if f.flavour_key == flavor or f.extId == flavor:
                    flavor_id = f.extId
                    used_flavor = f
                    break
            else:
                raise Exception('Not found flavor {} in VIM instance {}'.format(flavor, vim_instance.get('name')))
            # find correct availability zone
            zone_name = None
            try:
                zone_name = vim_instance.get('metadata').get('az')
            except AttributeError:
                pass
            if zone_name is not None:
                zones = self.list_availability_zones(vim_instance, nova_client)
                for z in zones:
                    if z.name == zone_name:
                        zone = z
                        break
                else:
                    zone_name = None
            # check key pair
            if keypair is not None and keypair != '':
                keys = self.list_keys(vim_instance, nova_client)
                for key in keys:
                    if key.name == keypair:
                        break
                else:
                    raise Exception('Keypair {} not found in VIM instance {}'.format(keypair, vim_instance.get('name')))
            # create server
            server = nova_client.servers.create(name=name, image=image.extId, flavor=flavor_id, key_name=keypair,
                                                availability_zone=zone_name, security_groups=security_groups,
                                                nics=nics, userdata=user_data)
            return server

        except:
            for port in ports:
                try:
                    neutron_client.delete_port(port.get('port').get('id'))
                except Exception as e:
                    log.error('Unable to delete the created port: {}'.format(e))
            raise

    def launch_instance_and_wait(self,
                                 vim_instance: dict,
                                 instance_name: str,
                                 image: str,
                                 flavor: str,
                                 key_pair: str,
                                 networks: [dict],
                                 security_groups: [str],
                                 user_data: str,
                                 floating_ips: dict = None,
                                 keys: [dict] = None):

        user_data = '' if user_data is None else user_data
        if keys is not None and len(keys) > 0:
            user_data += '\nfor x in `find /home/ -name authorized_keys`; do\n\techo \"' + \
                         '\" >> $x\n\techo \"'.join([keys.get(k).get('publicKey') for k in keys]) + \
                         '\" >> $x\ndone\n'
        nova_client = self.get_nova_client(vim_instance)
        server = self.__create_server(vim_instance, instance_name, image, flavor, key_pair, networks, security_groups,
                                      user_data,
                                      nova_client=nova_client)

        # wait until the server is active
        i = 0
        while i < self.wait_for_vm or self.wait_for_vm < 0:
            if self.__server_is_active(server):
                break
            time.sleep(1)
            server = nova_client.servers.get(server.id)
        else:
            if not self.__server_is_active(server):
                raise Exception(
                    'Timeout: after {} seconds the VM {} is still not active'.format(self.wait_for_vm, server.name))

        return self.__os_server_to_ob_server(server, self.list_images(vim_instance), self.list_flavors(vim_instance))

    def __server_is_active(self, server):
        if server.status.lower() == 'active':
            logging.info('VM {} is now active'.format(server.name))
            return True
        elif server.status.lower() == 'error':
            error_message = 'VM {} is in error state'.format(server.name)
            log.error(error_message)
            raise Exception(error_message)
        return False

    def delete_server_by_id_and_wait(self, vim_instance: dict, ext_id: str):
        nova_client = self.get_nova_client(vim_instance)
        neutron_client = self.get_neutron_client(vim_instance)
        server = nova_client.servers.get(ext_id)
        fips_to_delete = []
        if self.deallocate_floating_ips:
            log.info('Deallocating floating IP of VM {}'.format(ext_id))
            for network in server.addresses:
                for entry in server.addresses.get(network):
                    if entry.get('OS-EXT-IPS:type') == 'floating':
                        fips = neutron_client.list_floatingips().get('floatingips')
                        for fip in fips:
                            if entry.get('addr') == fip.get('floating_ip_address'):
                                try:
                                    neutron_client.delete_floatingip(fip.get('id'))
                                except Exception as e:
                                    log.error(
                                        'Exception while deallocating floating IP {}: {}'.format(entry.get('addr'), e))
                                break

        log.info('Deleting ports associated to VM {}'.format(ext_id))
        ports = neutron_client.list_ports().get('ports')
        for port in ports:
            if port.get('device_id') == ext_id:
                try:
                    neutron_client.delete_port(port.get('id'))
                except Exception as e:
                    log.error('Exception while removing port {}:{}'.format(port.get('id'), e))
        try:
            nova_client.servers.delete(server)
            log.info('Removed VM {} ({})'.format(server.name, server.id))
        except Exception as e:
            log.error('Exception while removing VM {} ({}): {}'.format(server.name, server.id, e))

    def __get_compute_quota(self, vim_instance, nova_client=None):
        if nova_client is None:
            nova_client = self.get_nova_client(vim_instance)
        tenant_id = vim_instance.get('tenant')
        quota = nova_client.quotas.get(tenant_id)
        return quota

    def __get_network_quota(self, vim_instance, neutron_client=None):
        if neutron_client is None:
            neutron_client = self.get_neutron_client(vim_instance)
        tenant_id = vim_instance.get('tenant')
        quota = neutron_client.show_quota(tenant_id)
        return quota

    def get_quota(self, vim_instance: dict):
        compute_quota = self.__get_compute_quota(vim_instance)
        net_quota = self.__get_network_quota(vim_instance).get('quota')
        quota = {}
        quota['tenant'] = vim_instance.get('tenant')
        quota['cores'] = compute_quota.cores
        quota['floatingIps'] = net_quota.get('floatingip')
        quota['instances'] = compute_quota.instances
        quota['keyPairs'] = compute_quota.key_pairs
        quota['ram'] = compute_quota.ram
        return quota

    def __find_connected_external_network(self, network_id, networks: [dict], routers: [dict], ports: [dict]):
        """
        Returns the ID of an external network that is connected to the network with the passed network_id.
        If no external network is found an Exception is raised.
        We assume that the network is directly attached to a router which is connected to an external network.

        :param network_id: the ID of the network for which a connected external network is searched
        :param networks: list of available networks in OpenStack
        :param routers: list of OpenStack routers
        :param ports: list of OpenStack ports
        :return: the ID of the connected external network
        """
        external_networks = [net for net in networks if net.get('external') is True]
        for ext_net in external_networks:
            connected_networks = [port.get('network_id') for port in ports if
                                  port.get('device_id') in [r.get('id') for r in routers]]
            if network_id in connected_networks:
                return ext_net.get('extId')
        raise Exception('No external network found connected to network {}'.format(network_id))


def main():
    path_to_file = os.path.abspath(os.path.dirname(__file__))
    conf_example_path = os.path.join(path_to_file, 'etc/configuration.ini')
    help_epilog = 'This is how the content of the configuration file could look like:\n\n'
    try:
        with open(conf_example_path, 'r') as conf_example_file:
            help_epilog += conf_example_file.read()
        help_epilog += ' \n\n'
    except Exception:
        help_epilog = None

    parser = argparse.ArgumentParser(description='This is an Open Baton VIM Driver for OpenStack written in Python',
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=help_epilog)
    parser.add_argument('-t', '--type', type=str, help='the type of the VIM driver, default is openstack',
                        default="openstack")
    parser.add_argument('-w', '--worker_threads', type=int,
                        help='the maximum number of threads for processing requests, default is 100', default=100)
    parser.add_argument('-l', '--listener_threads', type=int,
                        help='the number of threads consuming messages from RabbitMQ, default is 1', default=1)
    parser.add_argument('-r', '--reply_threads', type=int,
                        help='the number of threads for sending replies to the NFVO, default is 1', default=1)
    parser.add_argument('-n', '--name', type=str,
                        help='the name of the VIM driver, default is the VIM driver\'s <type>', default="")
    parser.add_argument('-c', '--conf-file', type=str, default="",
                        help='configuration_file location, default is /etc/openbaton/<type>_vim_driver.ini')

    args = parser.parse_args()
    plugin_type = args.type
    config_file_location = args.conf_file
    maximum_worker_threads = args.worker_threads
    number_listener_threads = args.listener_threads
    number_reply_threads = args.reply_threads
    name = args.name
    if not name:
        name = plugin_type
    conf_map = {}
    if not config_file_location:
        config_file_location = '/etc/openbaton/{}_vim_driver.ini'.format(plugin_type)
    if not os.path.exists(config_file_location):
        sys.stderr.write('Configuration file {} does not exist.\n'.format(config_file_location))
        sys.exit(1)

    with open(config_file_location, 'rt') as f:
        try:
            logging.config.fileConfig(f, disable_existing_loggers=False)
        except Exception as e:
            sys.stderr.write('Error in logging configuration. Using the default configuration: {}\n'.format(e))
            logging.basicConfig()
        cp = configparser.ConfigParser()
        try:
            cp.read(config_file_location)
            conf_map = get_map('general', cp)
        except Exception as e:
            log.exception('Not able to read config file {}: {}'.format(config_file_location, e))

    vim_driver_args = (bool(conf_map.get('deallocate-floating-ip', True)),
                       int(conf_map.get('connection-timeout', 10)),
                       int(conf_map.get('wait-for-vm', 15)))
    log.debug(
        'vim_driver_args: deallocate-floating-ip={}, connection-timeout={}, wait-for-vm={}'.format(vim_driver_args[0],
                                                                                                   vim_driver_args[1],
                                                                                                   vim_driver_args[2]))

    log.info('Starting the OpenStack Python VIM Driver')
    start_vim_driver(OpenstackVimDriver, config_file_location, maximum_worker_threads, number_listener_threads,
                     number_reply_threads, plugin_type, name, *tuple(vim_driver_args))
