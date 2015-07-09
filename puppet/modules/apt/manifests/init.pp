class apt {
  Package {
    require => Exec["sources update"]
  }

  exec { "sources update":
      command => "apt-get update",
      path => "/usr/bin:/usr/sbin:/bin",
      #refreshonly => true;
  }
  
}

class apt::allowunauthenticated inherits apt {

  file { "Apt allow unauthenticated":
      path => "/etc/apt/apt.conf.d/allow-unauthenticated",
      ensure => file,
      mode => 644, owner => root, group => root,
      content => "APT::Get::AllowUnauthenticated \"true\";\n";
  }

}
