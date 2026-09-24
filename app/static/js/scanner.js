/* Camera QR scanner for the gate page.
   Uses the jsQR library (loaded from a CDN in gate/index.html).
   Browsers only allow camera access on https:// or on http://localhost / 127.0.0.1. */

(function () {
    var toggle = document.getElementById("scan-toggle");
    var panel = document.getElementById("scanner");
    var video = document.getElementById("scanner-video");
    var canvas = document.getElementById("scanner-canvas");
    var statusText = document.getElementById("scanner-status");
    var input = document.getElementById("pass_code");
    var form = document.getElementById("lookup-form");

    if (!toggle || !panel || !video || !canvas) {
        return;
    }

    var stream = null;
    var running = false;

    function stop() {
        running = false;
        if (stream) {
            stream.getTracks().forEach(function (track) { track.stop(); });
            stream = null;
        }
        video.srcObject = null;
        panel.classList.add("hidden");
        toggle.textContent = "Scan with camera";
    }

    function tick() {
        if (!running) {
            return;
        }
        if (video.readyState === video.HAVE_ENOUGH_DATA && video.videoWidth > 0) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            var context = canvas.getContext("2d", { willReadFrequently: true });
            context.drawImage(video, 0, 0, canvas.width, canvas.height);
            var image = context.getImageData(0, 0, canvas.width, canvas.height);
            var result = window.jsQR ? window.jsQR(image.data, image.width, image.height) : null;
            if (result && result.data) {
                input.value = result.data.trim();
                stop();
                form.submit();
                return;
            }
        }
        requestAnimationFrame(tick);
    }

    function start() {
        if (!window.jsQR) {
            statusText.textContent = "The scanner library could not be loaded. Check the internet connection, or type the code.";
            panel.classList.remove("hidden");
            return;
        }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            statusText.textContent = "Camera access needs https:// or http://localhost. You can still type the code.";
            panel.classList.remove("hidden");
            return;
        }
        navigator.mediaDevices
            .getUserMedia({ video: { facingMode: "environment" }, audio: false })
            .then(function (mediaStream) {
                stream = mediaStream;
                video.srcObject = mediaStream;
                return video.play();
            })
            .then(function () {
                running = true;
                panel.classList.remove("hidden");
                statusText.textContent = "Point the camera at the QR code.";
                toggle.textContent = "Stop camera";
                requestAnimationFrame(tick);
            })
            .catch(function () {
                statusText.textContent = "Could not open the camera. Allow camera access, or type the code.";
                panel.classList.remove("hidden");
            });
    }

    toggle.addEventListener("click", function () {
        if (running) {
            stop();
        } else {
            start();
        }
    });

    window.addEventListener("pagehide", stop);
})();
