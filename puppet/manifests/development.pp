
class development {
  include openssl
  include local_ca
  include geni-tools-delegate

  # gcf requirements
  package {
    ['python-m2crypto', 'python-dateutil', 'python-openssl', 'libxmlsec1', 'xmlsec1', 'libxmlsec1-openssl', 'libxmlsec1-dev']:
      ensure => installed;
  }

  # configure gcf to be quickly usable from the vagrant account
  file { "/home/vagrant/.bash_aliases":
    ensure => present,
    mode => 750, owner => 'vagrant', group => 'vagrant',
    content => "
if [ -d \"/opt/geni-tools/src\" ] ; then
    PATH=\"/opt/geni-tools/src:/opt/geni-tools/src/examples:\$PATH\"
    export PATH
    export PYTHONPATH=\"/opt/geni-tools/src:\$PYTHONPATH\" 
fi

alias omni='omni.py'
alias omni-configure='omni-configure.py'
alias readyToLogin='readyToLogin.py'
alias clear-passphrases='clear-passphrases.py'
alias stitcher='stitcher.py'
alias remote-execute='remote-execute.py'
alias addMemberToSliceAndSlivers='addMemberToSliceAndSlivers.py'\n"  }
}
  

stage { "init": before  => Stage["main"] }

class {"apt": 
  stage => init,
}

include development
