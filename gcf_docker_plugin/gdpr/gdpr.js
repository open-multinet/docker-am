
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

            document.getElementById("basic_accept").checked = accepts.accept_basic;
            document.getElementById("userdata_accept").checked = accepts.accept_userdata;

            document.getElementById("testbed-denied").hidden = accepts.testbed_access;
            document.getElementById("testbed-allowed").hidden = !accepts.testbed_access;

            document.getElementById("until-date").innerHTML = accepts.until;
        } else {
            console.log("load_info onload FAILURE status="+this.status);
        }
    };
    xhttp.open("GET", "/gdpr/accept", true);
    xhttp.send();
}

function on_toggle_accept(event) {
//    console.log("on_toggle_accept()");
    var basic_accept = document.getElementById("basic_accept").checked;
    var userdata_accept = document.getElementById("userdata_accept").checked;
    var terms = {
        'accept_basic': basic_accept,
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
}

window.onload = function() {
    load_info();
}