# Supported Aggregate Manager features

* Every basic feature (Allocate, Provision, Delete, Status, ListResources, Describe, Renew)
* Some ```PerformOperationalAction``` call are supported
	* ```geni_update_users``` : Update SSH authorized keys or add a user
	* ```geni_reload``` : If you want to "reset" your container
	* Other options have no effect
* You can provide a sliver-type to get different kind of containers (for example limited memory or CPU container).
* Install a custum docker image by providing a name from a DockerHub or a URL to a Dockerfile or a ZipFile containing a Dockerfile and dependencies.
* Restart the AM without lost the state of slivers
* Multiple physical host for Docker. That means you can increase the scalability easily by setting up a new "DockerMaster"
* ```install``` and ```execute``` can be used to install a zipfile in a specific directory and execute some commands automatically when the container is ready
* IPv6 per container can be configured in addition to the IPv4 port forwarding of the host

# How to install the AM ?

## Dependencies

```
apt-get install -y python2.7 python-lxml git python-m2crypto python-dateutil python-openssl libxmlsec1 xmlsec1 libxmlsec1-openssl libxmlsec1-dev python-pip
```

```pip install pyro4```


## Download source code

* Firstly clone the git repository

```
git clone https://github.com/ArthurGarnier/bootstrap-geni-am.git
```

* Initialize submodule (geni-tools source code)

```
cd bootstrap-geni-am
cd geni-tools
git submodule init
git submodule update
git checkout develop
```

## Configure AM

Two files are used to configure the AM.

### gcf_config

Path of this file : ```bootstrap-geni-am/gcf\_docker\_plugin/gcf_config```

* base_name : Generally the name of your machine. This is the name used in the URN (urn:publicid:IDN+docker.ilabt.iminds.be+)
* rootcadir : A directory where your trusted root certificates are (wall2.pem for example)
* host : This should be the DNS name of the server. It is not only used for binding the server socket, it is also used in the GetVersion reply as server URL. 
* port : You are free to choose a port. 443 is recommended (because it is infrequently blocked by client side firewalls).
* delegate : Must be = testbed.ReferenceAggregateManager
* keyfile and certfile = Field used to create AM certificate

### delegate_config

Path of this file : ```bootstrap-geni-am/gcf\_docker\_plugin/delegate_config```

Each "section" (a section start with "[name\_of\_the\_section]") in this file represents a DockerMaster (a dockermaster host one or more containers). If you want to configure multiple DockerMaster just duplicate the first section and change the name. Then, configure parameters :

* max_containers : The maximum number of container hosted by your DockerMaster
* ipv6_prefix : If you have an ipv6 address on your host set the prefix in /64 or /80 (for example : 2607:f0d0:1002:51::) and each container will get a ipv6 in this range
* host, password and port : Parameters to connect to the dockermanager daemon (when using a remote dockermanager, see below)
* public_host : The ipv4 of your DockerMaster host (will be used to join containers with port forwarding and control the DockerMaster from the AM with SSH)
* starting\_ipv4\_port : This is the first range used by docker for port forwarding. For example if you set 12000, the first container should be reachable on port 12000, the second on port 12001, ... The AM uses the first port available from 12000 to 12000+max\_containers

## Configure a DockerMaster

Firstly, install the docker engine : https://docs.docker.com/engine/installation/

Then, make sure the daemon is running (with systemd) : ```systemctl start docker.service```

If you want the docker daemon restart automatically after reboot : ```systemctl enable docker.service```

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


# Starting the AM

```sh bootstrap-geni-am/run_am.sh```

Or with the systemd service : ```cp am_docker.service /etc/systemd/system/```

Edit the WorkingDirectory according to your installation, reload the systemd daemon : ```systemctl daemon-reload```, then start the AM : ```systemctl start am_docker.service```

Check the status : ```systemctl status am_docker.service```

# Trust your C-BAS installation

If you use C-BAS as Member Authority (MA) and Slice Authority (SA), you have to trust credentials from this. To do, just copy certificates used by C-BAS in your "rootcadir" (configured in gcf_config), usually there stored ```C-BAS/deploy/trusted/certs```.

Restart your AM, if you check the output of the server you should have this at the beginning :

```
INFO:cred-verifier:Adding trusted cert file sa-cert.pem
INFO:cred-verifier:Adding trusted cert file ma-cert.pem
INFO:cred-verifier:Adding trusted cert file ch-cert.pem
INFO:cred-verifier:Adding trusted cert file ca-cert.pem
INFO:cred-verifier:Combined dir of 4 trusted certs /root/C-BAS/deploy/trusted/certs/ into file /root/C-BAS/deploy/trusted/certs/CATedCACerts.pem for Python SSL support
```

Of course it's not C-BAS dependent and you can trust the certificate from any MA/SA. For example you can trust the MA/SA from iMinds, so you will be able to create a slice on wall2 and use it on your AM.

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
git clone https://github.com/ArthurGarnier/bootstrap-geni-am.git
```

And try : ```python2 bootstrap-geni-am/gcf_docker_plugin/daemon_dockermanager.py --host 127.0.0.1```

You should get a warning about not using any password and a URI the server listening on.

You can use it in this way but it's more convenient to configure a systemd service. To do this, just copy the service file :

```cp bootstrap-geni-am/dockermanager.service.sample /etc/systemd/system/dockermanager.service```

Then edit the WorkingDirectory and ExecStart line to match to your configuration. The "--host" parameter should be an IP reachable from the AM, so a public IP or, if your AM is on the same network a private IP.

Finally, do ```systemctl daemon-reload && systemctl start dockermanager.service``` and check with ```systemctl status dockermanager.service```

## Configure the AM

Just edit ```bootstrap-geni-am/gcf_docker_plugin/delegate_config``` and add or edit a section to match the three parameters (host, password, port) with the parameters set above (on the remote)

Then delete ```data.dat``` and restart your AM

# How to adapt this AM to your infrastructure ?

If you want to test the AM with your hardware (not with Docker) you have to develop your own Python Class which represents your hardware.

You can follow the docker model as example. It is based on three classes : DockerMaster (dockermaster.py), DockerContainer (dockercontainer.py), and DockerManager (gcf\_to\_docker.py).

* DockerMaster is more or less just a pool of DockerContainer, because a DockerMaster should be a unique physical machine
* DockerContainer represents a docker container, with some informations like to ssh port, the ipv6, ...
* DockerManager is just a generic class to manage docker from Python

So, if you want to represent a physical machine which can be reserved by a user the Python class should be a merge between ```DockerMaster``` and ```DockerContainer```, you should inherit your class from ```ExtendedResource```. This class is formed of all used methods by the AM, so you have to implement at least those methods (also have a look to ```geni-tools/src/gcf/geni/am/resource.py```)

Note : You should implement a generic wrapper for your infrastructure like ```DockerManager```, it's easier to maintain, especially if you have different kind of resource.

Once your resources are ready, you have to init them in ```testbed.py``` in the ```_init_``` method by adding them to the aggregate and delete ```data.dat``` if exists.


# Additional informations

* Objects are serialized in ```bootstrap-geni-am/data.dat```, so you can restart the AM without consequence
* Slivers expiration is checked every 5 minutes, and on each API call
* Warning : If you restart the host, docker containers are lost, to keep consistent state delete ```data.dat``` before restart the AM.
	* It should work without deleting the file but you could have some unexpected behaviors

# Troubleshooting

* If you get the error "Objects specify multiple slices", you probably made a typo in component\_manager\_id (during allocate call)
* If your configuration is not taken in account, delete ```bootstrap-geni-am/data.dat``` and remove running containers ```docker rm -f $(docker ps -a -q)```
* If you get an SSL error (like host not authenticated) check if you correctly add your AM/SA certs in trusted root


