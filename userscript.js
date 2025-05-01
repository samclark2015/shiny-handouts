// ==UserScript==
// @name    Panopto Handout Downloader
// @description Download Panopto Lecture as Handout
// @version 0.0.1
// @match   https://*.panopto.com/Panopto/Pages/Viewer.aspx*
// @require http://code.jquery.com/jquery-latest.js
// @require https://cdn.jsdelivr.net/npm/js-cookie@3.0.5/dist/js.cookie.min.js
// @grant   GM_cookie
// @grant   GM_registerMenuCommand
// ==/UserScript==


$(document).ready(function() {
    const onDownload = () => {
        GM_cookie.list({url: "", name: ".ASPXAUTH"}, async (cookie, error) => {
            if(error) {
                console.error(error);
                return;
            }

            const value = cookie[0].value;

            const url = new URL("https://sclark-posit.shinyapps.io/handout-generator/");
            url.searchParams.set("cookie", value);
            url.searchParams.set("url", document.location.href);

            window.open(url, "_blank");
        });
    }

    GM_registerMenuCommand("Generate Handout", onDownload);
});
