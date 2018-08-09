from setuptools import setup, find_packages


with open('README.md') as f:
    readme = f.read()

setup(
    name='openstack-vim-driver',
    version='6.0.0rc1',
    description='OpenStack VIM Driver for Open Baton',
    long_description=readme,
    long_description_content_type='text/markdown',
    url='https://github.com/openbaton/openstack-python-vim-driver',
    author="Open Baton",
    author_email="dev@openbaton.org",
    license='Apache 2',
    packages=find_packages(),
    install_requires=[
        'python-plugin-sdk',
        'python-glanceclient',
        'python-neutronclient',
        'python-novaclient',
        'requests'
    ],
    scripts=['openstack-vim-driver'],
    include_package_data=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Utilities',
        'License :: OSI Approved :: Apache Software License',
    ]
)
