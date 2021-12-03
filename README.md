# Supported Aggregate Manager features

* Every basic feature (Allocate, Provision, Delete, Status, ListResources, Describe, Renew)
* Some ```PerformOperationalAction``` call are supported
	* ```geni_update_users``` : Update SSH authorized keys or add a user
	* ```geni_reload``` : If you want to "reset" your container
	* Other options have no effect
* You can provide a sliver-type to get different kind of containers (for example limited memory or CPU container). Check the advertisement RSpec, and have a look at gcf_to_docker.py for details.
* Install a custum docker image by providing a name from a DockerHub or a URL to a Dockerfile or a ZipFile containing a Dockerfile and dependencies.
* Restart the AM without losing the state of existing slivers: Running docker containers will keep running when the AM stops, and can be controlled again when the AM restarts. (You can safely remove ```am-state-v1.dat``` to clear the state and thus force config reload. You will need to kill any running docker containers manually in that case.)
* Multiple physical host for Docker. That means you can increase the scalability easily by setting up a new "DockerMaster" on remote host. To scale the setup, integration with kubernetes is probably preferable.
* ```install``` and ```execute``` can be used to install a zipfile in a specific directory and execute commands automatically when the container is ready.
* IPv6 per container can be configured in addition to the IPv4 port forwarding of the host.
* The is demo code that can be used as a basis to customize the AM. Two features are demonstrated in this code:
** Supporting custom non-container external resources. (See resourceexample.py)
** Automatically adding a gateway proxy per slice. (See "proxy" in the configuration parsing)

# How to install the AM ?

## Dependencies

```
apt-get install -y python2.7 python-lxml git python-m2crypto python-dateutil python-openssl libxmlsec1 xmlsec1 libxmlsec1-openssl libxmlsec1-dev python-pip
```

Pyro4 is also required (for remote dockermasters):

```
pip install pyro4
```


## Download source code

* First clone the git repository

```
git clone https://github.com/open-multinet/docker-am.git
```

* Initialize submodule (geni-tools source code)

```
cd docker-am
cd geni-tools
git submodule init
git submodule update
git checkout develop
```

## Configure AM

Two files are used to configure the AM.

### gcf_config

This file is for the generic GCF configuration. This contains the basic AM setup. 
The docker AM specific functionality is activated by setting ```delegate``` to ```testbed.DockerAggregateManager```

Path of this file : ```docker-am/gcf\_docker\_plugin/gcf_config```

* base_name : Typically the name of your machine. This is the name used in the URN (``urn:publicid:IDN+docker.example.com+authority+am``)
* rootcadir : A directory where your trusted root certificates are stored. These are the certificates of the MA/SA servers who's users the AM will trust. (`portal_fed4fire_root_certificate.pem` for example). See also ["Allow users to use your AM"](#allow-users-to-use-the-am)
* host : This should be the DNS name of the server. It is used for binding the server socket. ```0.0.0.0``` is often a good choice if the hostname is not correctly configured on the server.
* port : You are free to choose a port. 443 is recommended (because it is infrequently blocked by client side firewalls).
* delegate : To activate the docker AM code, this must be ```testbed.DockerAggregateManager```
* keyfile and certfile = Private key and certificate of the AM server. This is used for SSL authentication. See the section below.

### docker_am_config

This is the configuration that is specific for the docker AM.

Path of this file : ```docker-am/gcf\_docker\_plugin/docker_am_config```

The ```[general]``` section currently contains one parameter.
* public_url: the URL to the AM, as advertised in the ```Getversion``` reply. This URL must contain the FQDN of the host. A raw IP address is discouraged. The following values for the hostname are forbidden here: ```0.0.0.0``` ```127.0.0.1``` ```localhost```

A ```[proxy]``` section is also allowed, but not mandatory (no automatic proxy is used if not specified). Check the example config for details.

Each other "section" in the config (a section start with ```[name\_of\_the\_section]```) in this file represents a DockerMaster (a dockermaster host one or more containers). If you want to configure multiple DockerMaster just duplicate the first section and change the name. Then, configure parameters :

* max_containers : The maximum number of container hosted by your DockerMaster
* ipv6_prefix : If you have an IPv6 address on your host, set the prefix in /64 or /80 (for example : 2607:f0d0:1002:51::) and each container will be assigned an IPv6 in this range
* dockermaster\_pyro4\_host, dockermaster\_pyro4\_password and dockermaster\_pyro4\_port : Parameters to connect to the dockermanager using pyro4 RPC (only when using a remote dockermanager, to use a local docker service, skip these options)
* node\_ipv4\_hostname : The IPv4 of your DockerMaster host (will be used to expose an SSH port on the containers)
* starting\_ipv4\_port : This is the first range used by docker for port forwarding. For example if you set 12000, the first container should be reachable on port 12000, the second on port 12001, ... The AM uses the first port available from 12000 to 12000+max\_containers

## Configure a DockerMaster

You can run the docker service on either the same node as the AM, or use the remote DockerMaster feature (which uses pyro4 for RPC) to run the service on another node.

On the node where docker needs to run, do the following:

First, install the docker engine: https://docs.docker.com/engine/installation/

Then, make sure the daemon is running (with systemd) : ```systemctl start docker.service```

If you want the docker daemon restart automatically after reboot : ```systemctl enable docker.service```

See the section "Configuring a remote DockerManager (Optional)" for more details on a remote DockerManager

### Configure IPv6 for Docker

If you want to use IPV6 on your container, you have to configure Docker bridge to use a specified prefix.

Create a new file (this path is available on Debian based distribution) ```/etc/systemd/system/docker/service.d/docker.conf``` :

```
[Service]
ExecStart=
ExecStart=/usr/bin/docker daemon --ipv6 --fixed-cidr-v6="2607:f0d0:1002:51::/64" -H fd://
```

By replacing the IPv6 example by your own with the proper prefix length (64 or 80)

Then restart your docker daemon : ```systemctl restart docker.service```

## Generate certificate and key

You need to get a server key and certificate for the AM. You can either get a real one (using your regular way to get SSL Certificate, or using "Let’s Encrypt"), or you can create a self signed AM server certificate. In the later case, you will need to add the self signed certificate to the trust store of all clients (which is not a big deal, as you need to add other server info anyway).

It is advised not to use the ```bootstrap-geni-am/geni-tools/src/gen-certs.py``` script provided by gcf, it does not generate a good AM server certificate.
A valid server certificate should have:
* A Subject Name containing a CN equal to the server hostname
* One or more Subject Alternative Names of type DNS matching the server hostname(s)
* The server hostname mentioned in the 2 points above, should be a DNS name, never a raw IP address
* There is no real need for the certificate to contain a Subject Alternative Name of type URI that contains the URN of the AM. But it is off course no problem if it is included.

Also note that your AM server certificate has nothing to do with the root certificate of your cleaninghouse (= MA/SA). The clearinghouse root certificate is used for trusting credentials and for SSL client authentication, it has nothing to do with SSL *server* authentication!

To generate a self signed server certificate, you can use the provided script:
```
cd generate-AM-server-cert/
./generate-certs.sh
```

Make sure the location of the server key and certificate matches the keyfile and certfile options specified in ```bootstrap-geni-am/gcf\_docker\_plugin/gcf_config```

You can find some more details on how a certificate can be generated at https://stackoverflow.com/a/27931596/404495 

# Allow users to use the AM

To allow users to use your AM, you need to add the root certificates that are used to sign these user's certificates to the AM's `rootcadir`.
That is the directory that contains PEM files of all the trusted root certificates.

You can find and change this directory in `gcf_config`, by default, it is:
```
# The directory that stores the trusted roots of your CH/AM 
# and those you have federated with
# This can be a relative or absolute path.
rootcadir=~/geni-tools/trusted_roots/
```

## Trust your federation root authority

Each user authority will provide a root certificate in PEM form, that you can add to `rootcadir`.

For example if you add the root CA certiciate from Fed4FIRE to your testbed `rootcadir`, all users of the [Fed4FIRE portal](https://portal.fed4fire.eu) will be able to create experiments on your testbed. 
You can find the Fed4FIRE root CA certificate here: https://portal.fed4fire.eu/root_certificate

Example commands:
```
cd ~/geni-tools/trusted_roots/
curl https://portal.fed4fire.eu/root_certificate > portal_fed4fire_root_certificate.pem
# now restart your AM
```

## Trust your C-BAS installation

If you use [C-BAS](blob/master/C-BAS_config.md) as Member Authority (MA) and Slice Authority (SA), you have to trust credentials from this. To do, just copy certificates used by C-BAS to your `rootcadir` (configured in `gcf_config`). The certificates are usually stored in `C-BAS/deploy/trusted/certs`.

Example:
```
cp -v C-BAS/deploy/trusted/certs/*.pem ~/geni-tools/trusted_roots/
```

The restart your AM. If you check the output of the server you should have this at the beginning :

```
INFO:cred-verifier:Adding trusted cert file sa-cert.pem
INFO:cred-verifier:Adding trusted cert file ma-cert.pem
INFO:cred-verifier:Adding trusted cert file ch-cert.pem
INFO:cred-verifier:Adding trusted cert file ca-cert.pem
INFO:cred-verifier:Combined dir of 4 trusted certs /root/C-BAS/deploy/trusted/certs/ into file /root/C-BAS/deploy/trusted/certs/CATedCACerts.pem for Python SSL support
```

# Starting the AM

```sh docker-am/run_am.sh```

Or with the systemd service : ```cp am_docker.service /etc/systemd/system/```

Edit the WorkingDirectory according to your installation, reload the systemd daemon : ```systemctl daemon-reload```, then start the AM : ```systemctl start am_docker.service```

Check the status : ```systemctl status am_docker.service```

# Configuring a remote DockerManager (Optional)

You can set up several DockerManager hosted on different physical machine in order to increase scalability (for example).

## Configure the remote

First of all you need to install dependancies on the remote host :

```
apt-get install python2.7 python-pip git
pip install pyro4
```

And install docker-engine : https://docs.docker.com/engine/installation/

Now download the source code repository :

```
git clone https://github.com/open-multinet/docker-am.git
```

And try : ```python2 docker-am/gcf_docker_plugin/daemon_dockermanager.py --host 127.0.0.1```

You should get a warning about not using any password and a URI the server listening on.

You can use it in this way but it's more convenient to configure a systemd service. To do this, just copy the service file :

```cp bootstrap-geni-am/dockermanager.service.sample /etc/systemd/system/dockermanager.service```

Then edit the WorkingDirectory and ExecStart line in this file to match to your configuration. The "--host" parameter should be an IP reachable from the AM, so a public IP or, if your AM is on the same network a private IP.

Finally, do ```systemctl daemon-reload && systemctl start dockermanager.service``` and check with ```systemctl status dockermanager.service```

## Configure the AM

On the AM, edit ```docker-am/gcf_docker_plugin/docker_am_config``` and add or edit a section to match the three parameters (dockermaster_pyro4_host, dockermaster_pyro4_password, dockermaster_pyro4_port) with the parameters set on the remote

Then delete ```am-state-v1.dat``` (to force configuration reload) and restart your AM.

# How to adapt this AM to your infrastructure ?

If you want to test the AM with your hardware (not with Docker or in addition to Docker) you have to develop your own Python Class which manages your hardware.

You can follow the docker model as example. It is based on three classes : DockerMaster (dockermaster.py), DockerContainer (dockercontainer.py), and DockerManager (gcf\_to\_docker.py).

* DockerMaster is more or less just a pool of DockerContainers, because a DockerMaster should be a unique physical machine
* DockerContainer represents a single docker container, with some information like to ssh port, the IPv6, ...
* DockerManager is a generic class to manage docker from Python

So, if you want to represent a physical machine which can be reserved by a user the Python class should be a merge between ```DockerMaster``` and ```DockerContainer```, 
you should inherit your class from ```ExtendedResource```. This class is formed of all used methods by the AM, 
so you have to implement at least those methods (also have a look to ```geni-tools/src/gcf/geni/am/resource.py```)

To kickstart coding this, the class "ResourceExample" is provided. 
It's dummy external resource manager, which can act as a starting template. 
You must write configuration processing code in ```testbed.py > _init_``` to enable the resource.
The dummy resource does nothing, to get started, edit the file ```resourceexample.py``` and find lines with ```ssh="exit 0;"``` and follow the instruction on the lines above. 
Note that the kickstart code assumes that your AM has SSH access to the external resource.

Once your resources are ready, you have to init them in ```testbed.py``` in the ```_init_``` method by adding them to the aggregate configuration parsing. 
Be sure to delete ```am-state-v1.dat``` when testing, to force configuration reload.

Note : You should probably implement a generic wrapper for your infrastructure like ```DockerManager```, 
it's easier to maintain, especially if you have different kinds of resources.

# Development notes

If you want make some contribution to this software, here there is a quick explanation of each file :

* testbed.py : The aggregate manager main class, handle calls from the API
* dockermaster.py : Docker Master is a pool of docker container, it is called to get some DockerContainer instances
* dockercontainer.py : Represents a Container with methods to manage it
* gcf\_to\_docker.py : The DockerManager class, used as generic wrapper for Docker in Python, mostly used by DockerContainer
* resourceexample.py : A dummy resource to kickstart you to develop your own resource
* extendedresource.py : A generic resource class which adds some usefull methods to the base Resource class (which is in ```resource.py```, in the geni-tools repo)
* daemon_dockermanager.py : The daemon used to create a remote DockerMaster using Pyro4 framework. 


# Additional informations

* Objects are serialized in ```docker-am/am-state-v1.dat```, so you can restart the AM without consequence
* Slivers expiration is checked every 5 minutes, and on each API call
* Warning : If you restart the host, docker containers are lost, to keep consistent state delete ```am-state-v1.dat``` before restarting the AM.
	* It will mostly work without deleting the file but you could have some unexpected behaviors

# Troubleshooting

* If you get the error "Objects specify multiple slices", you probably made a typo in ```component_manager_id``` (during allocate call)
* If your configuration is not taken in account, delete ```docker-am/am-state-v1.dat``` and remove all running containers ```docker rm -f $(docker ps -a -q)```
* If you get an SSL error (like host not authenticated) check if you correctly add your AM/SA certs in trusted root
