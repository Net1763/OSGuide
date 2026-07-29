document.addEventListener("DOMContentLoaded", () => {
    const backButton = document.getElementById("guide-back-button");

    if (backButton) {
        backButton.addEventListener("click", () => {
            window.history.back();
        });
    }

    const params = new URLSearchParams(window.location.search);
    const appId = params.get("id");

    if (!appId) {
        window.location.href = "index.html";
        return;
    }

    document.body.dataset.appId = appId;

    const accordionButtons = document.querySelectorAll(
        ".guide-accordion-button"
    );

    accordionButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const expanded =
                button.getAttribute("aria-expanded") === "true";

            button.setAttribute(
                "aria-expanded",
                String(!expanded)
            );

            const content = button.nextElementSibling;

            if (!content) {
                return;
            }

            content.hidden = expanded;
        });
    });
});
