class local_ca {
  
  file { "/opt/localCA":
    mode => 755, owner => root, group => root,
    ensure => directory,
  }
  
  file { "/opt/localCA/private":
    require => File["/opt/localCA"],
    mode => 755, owner => root, group => root,
    ensure => directory,
  }

  file { "/opt/localCA/certs":
    require => File["/opt/localCA"],
    mode => 755, owner => root, group => root,
    ensure => directory,
  }
  
  file { "/opt/localCA/newcerts":
    require => File["/opt/localCA"],
    mode => 755, owner => root, group => root,
    ensure => directory,
  }
  
  file { "/opt/localCA/conf":
    require => File["/opt/localCA"],
    mode => 755, owner => root, group => root,
    ensure => directory,
  }
  
  file { "/opt/localCA/export":
    require => File["/opt/localCA"],
    mode => 755, owner => root, group => root,
    ensure => directory,
  }
  
  file { "/opt/localCA/csr":
    require => File["/opt/localCA"],
    mode => 755, owner => root, group => root,
    ensure => directory,
  }
  
  file { "/opt/localCA/serial":
    require => Exec["Populate serial"],
    mode => 644, owner => root, group => root,
    ensure => file
  }

  exec { "Populate serial":
    require => File["/opt/localCA"],
    command => "/bin/echo \"01\"> /opt/localCA/serial",
    creates => "/opt/localCA/serial",
    user => root, group => root,
  }  
  
  file { "/opt/localCA/index.txt":
    require => File["/opt/localCA"],
    mode => 644, owner => root, group => root,
    ensure => file
  }

  exec { "Generate certificate authority":
    command => "/usr/bin/openssl req -new -x509 -days 3650 -keyform PEM -keyout /opt/localCA/private/cakey.pem -outform PEM -out /opt/localCA/certs/ca.pem -passout file:/etc/ssl/secret -batch -subj \"${x509_base_subj}/CN=local_ca/emailAddress=${am_staff_mail}\"",
    user => root, group => root,
    require => File["/etc/ssl/secret","/opt/localCA/private","/opt/localCA/certs/"],
    creates => "/opt/localCA/private/cakey.pem",
    cwd => "/opt"
  }


  exec { "Create debug user key and csr":
    user => vagrant, group => vagrant,
    require => File["/etc/ssl/userssl.cnf","/home/vagrant/secret"],
    command => "/usr/bin/openssl req -new -newkey rsa:2048 -keyout /home/vagrant/userkey.pem -out /home/vagrant/usercsr.pem -passout file:/home/vagrant/secret -batch -subj \"${x509_base_subj}/CN=${debug_user}/emailAddress=${am_staff_mail}\"",
    environment => ["OPENSSL_CONF=/etc/ssl/userssl.cnf"],
    creates => "/home/vagrant/usercsr.pem",
    cwd => "/opt"
  }

  exec { "Sign user csr":
    user => root, group => root,
    require => Exec["Create debug user key and csr"],
    command => "/usr/bin/openssl x509 -days 3650 -CA /opt/localCA/certs/ca.pem -CAkey /opt/localCA/private/cakey.pem -req -in /home/vagrant/usercsr.pem -outform PEM -out /home/vagrant/usercert.pem -CAserial /opt/localCA/serial -extfile /etc/ssl/userssl.cnf -extensions usr_cert -passin file:/etc/ssl/secret",
    environment => ["OPENSSL_CONF=/etc/ssl/userssl.cnf"],
    creates => "/home/vagrant/usercert.pem",
    cwd => "/opt"
  }

  file {"/home/vagrant/usercert.pem":
    owner => $am_user,
    group => $am_user,
    mode => 0600,
    require => Exec["Sign user csr"]
  }
}
