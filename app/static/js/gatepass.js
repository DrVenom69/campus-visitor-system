/* Campus Gate Pass - dashboard JavaScript */

document.addEventListener("DOMContentLoaded", function () {
    // Mobile sidebar toggle (the hamburger button existed in the design,
    // and dashboard.css already has a .sidebar.open state, but nothing wired them together)
    var menuButton = document.querySelector(".mobile-menu");
    var sidebar = document.querySelector(".sidebar");

    if (menuButton && sidebar) {
        menuButton.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });

        // Close the sidebar when tapping outside of it on mobile
        document.addEventListener("click", function (event) {
            if (
                sidebar.classList.contains("open") &&
                !sidebar.contains(event.target) &&
                !menuButton.contains(event.target)
            ) {
                sidebar.classList.remove("open");
            }
        });
    }
});
