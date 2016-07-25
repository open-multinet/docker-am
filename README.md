# How to install the AM ?

## Dependencies

```
apt-get install -y python2.7 python-lxml git python-m2crypto python-dateutil python-openssl libxmlsec1 xmlsec1 libxmlsec1-openssl libxmlsec1-dev
```

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

Path of this file : bootstrap-geni-am/gcf\_testbedname\_plugin/gcf_config

* base_name : Generally the name of your machine. This is the name used in the URN (urn:publicid:IDN+docker.ilabt.iminds.be+)
* rootcadir : A directory where your trusted root certificates are (wall2.pem for example)
* host : Without proxy it should be 0.0.0.0 (listen on all interfaces/addresses)
* port : Usually is 8001 but what you want
* delegate : Must be = testbed.ReferenceAggregateManager
* keyfile and certfile = Field used to create AM certificate

### delegate_config

Path of this file : bootstrap-geni-am/gcf\_testbedname\_plugin/delegate_config

Each "section" (a section start with "[name\_of\_the\_section]") in this file represents a DockerMaster (a dockermaster host one or more containers). If you want to configure multiple DockerMaster just duplicate the first section and change the name. Then, configure parameters :

* max_containers : The maximum number of container hosted by your DockerMaster
* ipv6_prefix : If you have an ipv6 address on your host set the prefix in /64 or /80 (for example : 2607:f0d0:1002:51::) and each container will get a ipv6 in this range
* host : The ipv4 of your DockerMaster host (will be used to join containers with port forwarding and control the DockerMaster from the AM with SSH)
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

Run :

```
python bootstrap-geni-am/geni-tools/src/gen-certs.py --am
```

File will be placed where specified in gcf_config (keyfile and certfile)

# Starting the AM

```sh bootstrap-geni-am/run_am.sh```
