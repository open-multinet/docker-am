
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
        } else {
            document.getElementById("debug").innerHTML = xhttp.responseText;
            document.getElementById("status").innerHTML = 'LOAD ERROR';
        }
    };
    xhttp.open("GET", "/gdpr/accept", true);
    xhttp.send();
}

function accept_terms() {
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
    xhr.send(''); //empty for now
}

function decline_terms() {
    console.log("decline_terms()");
    var xhttp = new XMLHttpRequest();
    xhttp.onreadystatechange = function() {
        console.log("decline_terms onreadystatechange readyState="+this.readyState+" status="+this.status);
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