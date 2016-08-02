# How to configure a C-BAS (SA + AM) from scratch working with jFed software suite

The testbed machine use Debian Jessie x64 distribution.

# C-BAS configuration

* Install dependencies :

```
apt-get install swig mongodb python-pip python-dev libffi-dev xmlsec1 git libssl-dev
```

* Copy git repo:

```
git clone https://github.com/EICT/C-BAS.git
```

* Edit C-BAS/requirements.txt : Change `cryptography==0.2.2` to `cryptography=0.6.1`

* Install python dependencies :

```
pip install -r C-BAS/requirements.txt
```

* Copy the following files and adjust the entries as required
   * The `C-BAS/deploy/config.json.example` to `deploy/config.json`
   * The `C-BAS/deploy/registry.json.example` to `deploy/registry.json`
   * The `C-BAS/deploy/supplementary_fields.json.example` to `deploy/supplimentary_fields.json`

* Generate certificates by running script available at test/creds/gen-certs.sh

```
sh C-BAS/test/creds/gen-certs.sh
```

## Run the server

Try to run `sh python C-BAS/src/main.py` it should write : `* Restarting with reloader`


You can also run it as a daemon with `C-BAS/cbas.sh start`

### Troubleshooting

#### pymongo.errors.ConnectionFailure: could not connect to localhost:27017: [Errno 111] Connection refused

This error means that your mongodb service is not running. Try to start it again `systemctl start mongodb.service` if something wrong happen again try to check the logs, but maybe you don't have enought space on /var (mongo needs about 3.5Go).
A **dirty** quick fix is edit the service file `/lib/systemd/system/mongodb.service` and add `--smallfiles` at the end of the line `ExecStart=/usr/bin/mongod --config /etc/mongodb.conf`

#### eisoil.core.pluginmanager.ServiceNotRegisteredError: ologgingauthorityrm (try looking at the log)

Means one or more dependencies are missing, check that you got no error during the installation of python dependencies !

# Add a user

The best way to add a user and get it's certificates is to use AdminTools, which requires Java on your computer. First of all you have to download root certificate from the server to your computer : `scp user@IP:C-BAS/admin/root-*.pem /tmp`

Then, run the tools : `java -jar C-BAS/javaadmintool/bin/admintool.jar`

The default port is 8008, root member certificate and key are in your /tmp (according to the scp command above). Then add a new user and save its certificate/key

## Troubleshooting

Certificates used by the server are weak, so Java 8 and higher refuse to connect to this one. To bypass this security edit `/usr/lib64/jvm/java/jre/lib/security/java.security` (for Debian based only else you can find the path by using `ls -l $(which java)`) and edit this lines :

* `jdk.certpath.disabledAlgorithms=MD2, MD5, RSA keySize < 1024` to `jdk.certpath.disabledAlgorithms=MD2, RSA keySize < 1024`
* `jdk.tls.disabledAlgorithms=SSLv3, RC4, MD5withRSA, DH keySize < 768` to `jdk.tls.disabledAlgorithms=SSLv3, RC4, DH keySize < 768`

Or manually generate a new stronger certificate for the server. <!-- Todo -->

# Configure jFed to use this MA and SA (jFed Probe)

Edit your ~/.jFed/autorities.xml and add :

```xml
<authority>
    <hrn>Test C-BAS</hrn>
    <urn>urn:publicid:IDN+MY_AUTHORITY+authority+cm</urn>
    <urls>
	<serverurl>
	<servertype role="GENI_CH_MA" version="2"/>
	<url>https://MY_HOST:8008/ma/2</url>
	</serverurl>
            <serverurl>
                <servertype role="GENI_CH_SA" version="2"/>
	<url>https://MY_HOST:8008/sa/2</url>
            </serverurl>
    </urls>
    <proxies/>
    <pemSslTrustCert>MY_CERTIFICATE</pemSslTrustCert>
    <allowedCertificateHostnameAliases>
        <alias>MY_AUTHORITY.authority.ch</alias>
    </allowedCertificateHostnameAliases>
     <special>must_reconnect_each_call</special>
</authority>
```

Where :

* MY_AUTHORITY is the authority you set when you generated the certs
* MY_HOST is the hostname/ip where the server is running
* MY_CERTIFICATE is the server certificate you can get with this command : `openssl s_client -connect MY_HOST:8008 -key /tmp/root-key.pem -cert /tmp/root-cert.pem` and copy the content under the section "server certificate" which is delimited by : -----BEGIN CERTIFICATE----- and -----END CERTIFICATE----- (the delimiters must be copied too)

In the previous section you created a user and get its certificate and key, to use them in jFed you should create a new file which contains both the cert and the key :

```
cp test-cert.pem test-jfed.pem
cat test-key.pem >> test-jfed.pem
```

Now you should be able to log in jFed with this user and contact the AM and SM in order to create project or slice for example. 
