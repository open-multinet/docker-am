
function set_loading(is_loading) {
//    console.log("set_loading("+is_loading+")");
    if (is_loading) {
        document.getElementById("userurn").innerHTML = 'loading...';
    } else {
        document.getElementById("userurn").innerHTML = '-';
    }

    document.getElementById("testbed-denied").hidden = true;
    document.getElementById("testbed-allowed").hidden = true;

    var loadedonce = document.getElementsByClassName("loadedonce");
    for(var i = 0; i < loadedonce.length; i++) {
        if (is_loading) {
           loadedonce.item(i).hidden = false;
       }
    }

    var loaded = document.getElementsByClassName("loaded");
    for(var i = 0; i < loaded.length; i++) {
       loaded.item(i).hidden = is_loading;
    }

    var loading = document.getElementsByClassName("loading");
    for(var i = 0; i < loading.length; i++) {
       loading.item(i).hidden = !is_loading;
//        if (!is_loading) {
//            loading.item(i).style.display = 'none';
//        } else {
//            loading.item(i).style.display = 'block';
//        }
    }
}

function load_info() {
//    console.log("load_info()");
    set_loading(true);
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        set_loading(false);
        if (this.status == 200) {
            var accepts = JSON.parse(xhttp.responseText);

            document.getElementById("userurn").innerHTML = accepts.user_urn;

            document.getElementById("main_accept").checked = accepts.accept_main;
            document.getElementById("userdata_accept").checked = accepts.accept_userdata;

            if (accepts.accept_main) {
                $('#main_accept').bootstrapToggle('on');
            } else {
                $('#main_accept').bootstrapToggle('off');
            }

            if (accepts.accept_userdata) {
                $('#userdata_accept').bootstrapToggle('on');
            } else {
                $('#userdata_accept').bootstrapToggle('off');
            }

            document.getElementById("testbed-denied").hidden = accepts.testbed_access;
            document.getElementById("testbed-allowed").hidden = !accepts.testbed_access;

            document.getElementById("until-date").innerHTML = accepts.until;

            //let jFed know
            if (window.jfed && window.jfed.approveWithDateISO8601 && window.jfed.decline) {
                if (accepts.testbed_access) {
                    window.jfed.approveWithDateISO8601(accepts.until);
                } else {
                    window.jfed.decline();
                }
            }
        } else {
            console.log("load_info onload FAILURE status="+this.status);
        }
    };
    xhttp.open("GET", "/gdpr/accept", true);
    xhttp.send();
}

function on_toggle_accept(event) {
//    console.log("on_toggle_accept()");
    var main_accept = document.getElementById("main_accept").checked;
    var userdata_accept = document.getElementById("userdata_accept").checked;
    var terms = {
        'accept_main': main_accept,
        'accept_userdata': userdata_accept
    };
    set_loading(true);
    send_accept_terms(terms);
}

function send_accept_terms(terms) {
//    console.log("send_accept_terms()");
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        if (this.status == 204) {
            load_info();
        } else {
            console.log("accept_terms onload FAILURE status="+this.status);
        }
    };
    xhttp.open("PUT", "/gdpr/accept", true);
    xhttp.setRequestHeader('Content-Type', 'application/json');
    xhttp.send(JSON.stringify(terms));
}

function decline_all_terms() {
    set_loading(true);
//    console.log("decline_all_terms()");
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        if (this.status == 204) {
            load_info();
        } else {
            console.log("decline_all_terms onload FAILURE status="+this.status);
        }
    };
    xhttp.open("DELETE", "/gdpr/accept", true);
    xhttp.send();

    if (window.jfed && window.jfed.decline) {
        window.jfed.decline();
    }
}

function initJFed() {
//  if (window.jfed && window.jfed.decline) {
//      //let jFed know the users hasn't accepted the Terms and Conditions yet.
//      window.jfed.decline();
//  }

  //nothing to do: load_info will set the stored info
}

window.onload = function() {
    if (window.jfed) {
      initJFed();
    } else {
      //window.jfed is not (yet) available
      //trick to make browser call  initJFed() when window.jfed becomes available.
      Object.defineProperty(window, 'jfed', {
        configurable: true,
        enumerable: true,
        writeable: true,
        get: function() {
          return this._jfed;
        },
        set: function(val) {
          this._jfed = val;
          initJFed();
        }
      });

      if (window.jfed) {
        initJFed();
      }
    }

    load_info();
}
