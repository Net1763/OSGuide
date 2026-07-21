'use strict';

/* =========================================
   OSGuide — Main JavaScript
========================================= */

document.addEventListener('DOMContentLoaded', () => {
    const body = document.body;

    const searchInput = document.getElementById('app-search');
    const clearSearchButton = document.getElementById('clear-search-button');
    const searchResults = document.getElementById('search-results');
    const applicationsGrid = document.getElementById('applications-grid');
    const applicationCount = document.getElementById('application-count');
    const emptyState = document.getElementById('empty-state');

    const newestButton = document.getElementById('newest-button');
    const themeButton = document.getElementById('theme-button');
    const guideButton = document.getElementById('guide-button');
    const fdroidInfoButton = document.getElementById('fdroid-info-button');

    const applicationModal = document.getElementById('application-modal');
    const fdroidModal = document.getElementById('fdroid-modal');
    const guideModal = document.getElementById('guide-modal');

    const applicationCards = Array.from(
        document.querySelectorAll('.application-card')
    );

    const modals = [
        applicationModal,
        fdroidModal,
        guideModal
    ].filter(Boolean);

    let newestFirst = true;

    /* =====================================
       Theme
    ===================================== */

    const savedTheme = localStorage.getItem('osguide-theme');
    const systemUsesDarkMode = window.matchMedia(
        '(prefers-color-scheme: dark)'
    ).matches;

    if (
        savedTheme === 'dark' ||
        (!savedTheme && systemUsesDarkMode)
    ) {
        body.classList.add('dark-mode');
    }

    updateThemeButtonLabel();

    themeButton?.addEventListener('click', () => {
        body.classList.toggle('dark-mode');

        const selectedTheme = body.classList.contains('dark-mode')
            ? 'dark'
            : 'light';

        localStorage.setItem('osguide-theme', selectedTheme);
        updateThemeButtonLabel();
    });

    function updateThemeButtonLabel() {
        if (!themeButton) {
            return;
        }

        const darkModeEnabled = body.classList.contains('dark-mode');

        themeButton.setAttribute(
            'aria-label',
            darkModeEnabled
                ? 'Switch to light mode'
                : 'Switch to dark mode'
        );

        themeButton.setAttribute(
            'title',
            darkModeEnabled
                ? 'Switch to light mode'
                : 'Switch to dark mode'
        );
    }

    /* =====================================
       Modal System
    ===================================== */

    function openModal(modal) {
        if (!modal) {
            return;
        }

        closeAllModals();

        modal.hidden = false;
        body.classList.add('modal-open');

        const firstFocusableElement = modal.querySelector(
            'button, a, input, [tabindex]:not([tabindex="-1"])'
        );

        window.setTimeout(() => {
            firstFocusableElement?.focus();
        }, 50);
    }

    function closeModal(modal) {
        if (!modal) {
            return;
        }

        modal.hidden = true;

        const anyModalOpen = modals.some(
            currentModal => currentModal.hidden === false
        );

        if (!anyModalOpen) {
            body.classList.remove('modal-open');
        }
    }

    function closeAllModals() {
        modals.forEach(modal => {
            modal.hidden = true;
        });

        body.classList.remove('modal-open');
    }

    document.querySelectorAll('[data-close-modal]').forEach(button => {
        button.addEventListener('click', () => {
            const modal = button.closest('.modal');
            closeModal(modal);
        });
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            closeAllModals();
        }
    });

    guideButton?.addEventListener('click', () => {
        openModal(guideModal);
    });

    fdroidInfoButton?.addEventListener('click', () => {
        openModal(fdroidModal);
    });

    document.querySelectorAll('[data-open-app]').forEach(button => {
        button.addEventListener('click', () => {
            openModal(applicationModal);
        });
    });

    document.querySelectorAll('[data-download-app]').forEach(button => {
        button.addEventListener('click', event => {
            event.stopPropagation();
            openModal(applicationModal);
        });
    });

    /* =====================================
       Live Search
    ===================================== */

    searchInput?.addEventListener('input', () => {
        const query = normalizeText(searchInput.value);

        clearSearchButton.hidden = query.length === 0;

        filterApplications(query);
        renderSearchSuggestions(query);
    });

    clearSearchButton?.addEventListener('click', () => {
        if (!searchInput) {
            return;
        }

        searchInput.value = '';
        clearSearchButton.hidden = true;
        searchResults.hidden = true;

        filterApplications('');
        searchInput.focus();
    });

    function filterApplications(query) {
        let visibleApplications = 0;

        applicationCards.forEach(card => {
            const applicationName = normalizeText(
                card.dataset.appName || ''
            );

            const cardText = normalizeText(card.textContent || '');

            const matchesSearch =
                query.length === 0 ||
                applicationName.includes(query) ||
                cardText.includes(query);

            card.hidden = !matchesSearch;

            if (matchesSearch) {
                visibleApplications += 1;
            }
        });

        updateApplicationCount(visibleApplications);

        if (emptyState) {
            emptyState.hidden = visibleApplications !== 0;
        }

        if (applicationsGrid) {
            applicationsGrid.hidden = visibleApplications === 0;
        }
    }

    function renderSearchSuggestions(query) {
        if (!searchResults) {
            return;
        }

        searchResults.innerHTML = '';

        if (query.length === 0) {
            searchResults.hidden = true;
            return;
        }

        const matchingCards = applicationCards.filter(card => {
            const applicationName = normalizeText(
                card.dataset.appName || ''
            );

            return applicationName.includes(query);
        });

        if (matchingCards.length === 0) {
            searchResults.hidden = true;
            return;
        }

        matchingCards.slice(0, 5).forEach(card => {
            const applicationName =
                card.dataset.appName || 'Application';

            const suggestionButton = document.createElement('button');

            suggestionButton.type = 'button';
            suggestionButton.className = 'search-result-item';

            suggestionButton.innerHTML = `
                <div class="search-result-icon termux-icon">
                    <svg viewBox="0 0 64 64" aria-hidden="true">
                        <rect
                            width="64"
                            height="64"
                            rx="15"
                            fill="#15171c"
                        ></rect>

                        <path
                            d="M17 21L28 32L17 43"
                            fill="none"
                            stroke="white"
                            stroke-width="5"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                        ></path>

                        <path
                            d="M33 43H47"
                            stroke="white"
                            stroke-width="5"
                            stroke-linecap="round"
                        ></path>
                    </svg>
                </div>

                <div class="search-result-text">
                    <strong>${escapeHtml(applicationName)}</strong>
                    <span>Open application information</span>
                </div>
            `;

            suggestionButton.addEventListener('click', () => {
                searchInput.value = applicationName;
                clearSearchButton.hidden = false;
                searchResults.hidden = true;

                filterApplications(normalizeText(applicationName));

                card.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });

                window.setTimeout(() => {
                    openModal(applicationModal);
                }, 350);
            });

            searchResults.appendChild(suggestionButton);
        });

        searchResults.hidden = false;
    }

    /* =====================================
       Newest Sorting
    ===================================== */

    newestButton?.addEventListener('click', () => {
        if (!applicationsGrid) {
            return;
        }

        const sortedCards = [...applicationCards].sort(
            (firstCard, secondCard) => {
                const firstDate = new Date(
                    firstCard.dataset.added || 0
                ).getTime();

                const secondDate = new Date(
                    secondCard.dataset.added || 0
                ).getTime();

                return newestFirst
                    ? secondDate - firstDate
                    : firstDate - secondDate;
            }
        );

        sortedCards.forEach(card => {
            applicationsGrid.appendChild(card);
        });

        newestFirst = !newestFirst;

        newestButton.setAttribute(
            'aria-label',
            newestFirst
                ? 'Sort applications from newest to oldest'
                : 'Sort applications from oldest to newest'
        );
    });

    /* =====================================
       Login Placeholder Buttons
    ===================================== */

    document.querySelectorAll('.login-option').forEach(button => {
        button.addEventListener('click', () => {
            const originalText = button.textContent.trim();

            button.disabled = true;
            button.textContent = 'Coming in the authentication stage';

            window.setTimeout(() => {
                button.disabled = false;
                button.textContent = originalText;
            }, 1800);
        });
    });

    /* =====================================
       Initial State
    ===================================== */

    filterApplications('');
    updateApplicationCount(applicationCards.length);

    /* =====================================
       Utilities
    ===================================== */

    function updateApplicationCount(count) {
        if (!applicationCount) {
            return;
        }

        applicationCount.textContent =
            count === 1
                ? '1 application'
                : `${count} applications`;
    }

    function normalizeText(value) {
        return String(value)
            .trim()
            .toLocaleLowerCase();
    }

    function escapeHtml(value) {
        return String(value)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }
});
