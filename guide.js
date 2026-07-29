document.addEventListener("DOMContentLoaded", () => {

    const backButton = document.getElementById("guide-back-button");

    if (backButton) {
        backButton.addEventListener("click", () => {
            window.history.back();
        });
    }

    const accordionButtons = document.querySelectorAll(".guide-accordion-button");

    accordionButtons.forEach(button => {

        button.addEventListener("click", () => {

            const expanded = button.getAttribute("aria-expanded") === "true";

            button.setAttribute("aria-expanded", !expanded);

            const content = button.nextElementSibling;

            if (!content) return;

            if (expanded) {

                content.hidden = true;

            } else {

                content.hidden = false;

            }

        });

    });

});
