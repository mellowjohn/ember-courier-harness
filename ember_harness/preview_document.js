/* Shared by the local app and its Chromium inspection tools. */
(() => {
  const policy = "default-src 'none'; script-src 'unsafe-inline' data:; style-src 'unsafe-inline' data:; " +
    "img-src data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; " +
    "base-uri 'none'; form-action 'none'";

  function blockPeerConnections() {
    // connect-src does not control WebRTC. Run this before any project scripts.
    for (const name of ['RTCPeerConnection', 'webkitRTCPeerConnection', 'mozRTCPeerConnection']) {
      Object.defineProperty(window, name, { value: undefined, writable: false, configurable: false });
    }
  }

  function previewDocument(html) {
    return '<meta http-equiv="Content-Security-Policy" content="' + policy + '">' +
      '<script>(' + blockPeerConnections.toString() + ')();</script>' + html;
  }

  function inspectionBrowserOptions(executablePath) {
    // WebRTC can bypass HTTP interception, including from nested srcdoc frames.
    return {
      headless: true,
      chromiumSandbox: true,
      executablePath,
      args: [
        '--proxy-server=http://ember-offline.invalid:9',
        '--proxy-bypass-list=<-loopback>',
        '--host-resolver-rules=MAP * ~NOTFOUND',
        '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
      ],
    };
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { previewDocument, blockPeerConnections, inspectionBrowserOptions };
  } else {
    globalThis.previewDocument = previewDocument;
  }
})();
