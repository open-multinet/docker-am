class geni-tools-delegate {
  file { "/etc/geni-tools-delegate":
    ensure => directory,
    mode => 750, owner => $am_user, group => $am_user,
  }

  file { "/etc/geni-tools-delegate/gcf_config":
    ensure => present,
    mode => 750,  owner => $am_user, group => $am_user,
    require => File["/etc/geni-tools-delegate"],
    content => template("geni-tools-delegate/gcf_config")
  }
  file { "/etc/geni-tools-delegate/certs":
    ensure => directory,
    mode => 750, owner => $am_user, group => $am_user,
    require => File["/etc/geni-tools-delegate"]
  }

  exec { "Generate Aggregate manager private key and certificate request":
    command => "/usr/bin/openssl req -new -keyform PEM -keyout /etc/geni-tools-delegate/certs/am-key.pem -outform PEM -out /etc/geni-tools-delegate/certs/am-csr.pem -nodes -passin file:/etc/ssl/secret  -batch -subj \"${x509_base_subj}/CN=${fqdn}/emailAddress=${am_staff_mail}\"",
    user => root, group => root,
    require => File["/etc/geni-tools-delegate/certs", "/etc/ssl/openssl.cnf"],
    creates => "/etc/geni-tools-delegate/certs/am-csr.pem",
    cwd => "/opt"
  }

  file {"/etc/geni-tools-delegate/certs/am-key.pem":
    owner => $am_user,
    group => $am_user,
    mode => 0600,
    require => Exec["Generate Aggregate manager private key and certificate request"]
  }
  
  exec { "Sign am certificate":
    user => root, group => root,
    require => Exec["Generate Aggregate manager private key and certificate request","Generate certificate authority"], 
    command => "/usr/bin/openssl x509 -days 3650 -CA /opt/localCA/certs/ca.pem -CAkey /opt/localCA/private/cakey.pem -req -in  /etc/geni-tools-delegate/certs/am-csr.pem -outform PEM -out /etc/geni-tools-delegate/certs/am-cert.pem -CAserial /opt/localCA/serial -extfile /etc/ssl/openssl.cnf -extensions usr_cert -passin file:/etc/ssl/secret",
    creates => "/etc/geni-tools-delegate/certs/am-cert.pem",
    cwd => "/opt"
  }

  file {"/etc/geni-tools-delegate/certs/am-cert.pem":
    owner => $am_user,
    group => $am_user,
    mode => 0600,
    require => Exec["Sign am certificate"]
  }

  file { "/etc/geni-tools-delegate/certs/trusted_roots":
    ensure => directory,
    mode => 750, owner => $am_user, group => $am_user,
    require => File["/etc/geni-tools-delegate/certs"]
  }
  
  exec {"Install local ca as trusted root":
    require => [File["/etc/geni-tools-delegate/certs/trusted_roots"],
                Exec["Generate certificate authority"]],
    command => "/bin/cp /opt/localCA/certs/ca.pem /etc/geni-tools-delegate/certs/trusted_roots",
    user => $am_user, group => $am_user,
    creates => "/etc/geni-tools-delegate/certs/trusted_roots/ca.pem",
  }
  
  file { "/home/vagrant/secret":
    ensure => present,
    content => "$debug_user_pass\n",
    mode => 600, owner => $am_user, group => $am_user,
  }
}
