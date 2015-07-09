class openssl {

  package {
    ['ruby-uuidtools']:
    ensure => installed;
  }

  file { "/etc/ssl/openssl.cnf":
    ensure => present,
    mode => 644, owner => root, group => root,
    content => template("openssl/openssl.cnf"),
    require => Package['ruby-uuidtools']
  }

  file { "/etc/ssl/userssl.cnf":
    ensure => present,
    mode => 644, owner => root, group => root,
    content => template("openssl/userssl.cnf"),
    require => Package['ruby-uuidtools']
  }

  file { "/etc/ssl/secret":
    ensure => present,
    content => "$local_ca_pass\n",
    mode => 600, owner => root, group => root,
  }
  
}
