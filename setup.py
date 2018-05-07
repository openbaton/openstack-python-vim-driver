from setuptools import setup, find_packages


with open('README.rst') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

setup(
    name='openstack-vim-driver',
    version='0.1.0dev1',
    description='OpenStack VIM Driver for Open Baton',
    long_description=readme,
    url='https://github.com/openbaton/openstack-python-vim-driver',
    license=license,
    packages=find_packages(),
    install_requires=[
        'python-plugin-sdk',
        'python-glanceclient',
        'python-neutronclient',
        'python-novaclient'
    ],
    scripts=['etc/openstack-vim-driver']
)
