
function load_info() {
    console.log("load_info()");
    document.getElementById("status").innerHTML = 'loading...';
    document.getElementById("userurn").innerHTML = 'loading...';
    document.getElementById("debug").innerHTML = 'loading info...';

    var xhttp = new XMLHttpRequest();
    xhttp.onreadystatechange = function() {
        console.log("load_info onreadystatechange readyState="+this.readyState+" status="+this.status);
        if (this.readyState == 4 && this.status == 200) {
            document.getElementById("debug").innerHTML = xhttp.responseText;
            document.getElementById("status").innerHTML = 'loaded';
            document.getElementById("userurn").innerHTML = 'todo';

            document.getElementById("basic_accept").prop('checked', true).change(); //TODO
            document.getElementById("userdata_accept").prop('checked', true).change(); //TODO

            document.getElementById("testbed-denied").prop('hidden', true).change(); //TODO
            document.getElementById("testbed-allowed").prop('hidden', true).change(); //TODO
        } else {
            document.getElementById("debug").innerHTML = xhttp.responseText;
            document.getElementById("status").innerHTML = 'LOAD ERROR';
        }
    };
    xhttp.open("GET", "/gdpr/accept", true);
    xhttp.send();
}

function on_update_accept() {
    console.log("on_update_accept()");
    var basic_accept = document.getElementById("basic_accept").prop('checked');
    var userdata_accept = document.getElementById("userdata_accept").prop('checked');
    var terms = {
        'basic': basic_accept,
        'userdata': userdata_accept
    };
    send_accept_terms(terms);
}

function send_accept_terms(terms) {
    console.log("accept_terms()");
    var xhttp = new XMLHttpRequest();
    xhttp.onreadystatechange = function() {
        console.log("accept_terms onreadystatechange readyState="+this.readyState+" status="+this.status);
        if (this.readyState == 4 && this.status == 204) {
            load_info();
        } else {
            document.getElementById("debug").innerHTML = xhttp.responseText;
            document.getElementById("status").innerHTML = 'ACCEPT ERROR';
        }
    };
    xhttp.open("PUT", "/gdpr/accept", true);
    xhttp.setRequestHeader('Content-Type', 'application/json');
    xhr.send(JSON.stringify(terms));
}

function decline_all_terms() {
    console.log("decline_all_terms()");
    var xhttp = new XMLHttpRequest();
    xhttp.onreadystatechange = function() {
        console.log("decline_all_terms onreadystatechange readyState="+this.readyState+" status="+this.status);
        if (this.readyState == 4 && this.status == 204) {
            load_info();
        } else {
            document.getElementById("debug").innerHTML = xhttp.responseText;
            document.getElementById("status").innerHTML = 'DECLINE ERROR';
        }
    };
    xhttp.open("DELETE", "/gdpr/accept", true);
    xhttp.send();
}

load_info();