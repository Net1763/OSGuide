'use strict';

/* ==================================================
   OSGuide — Dynamic Application System
================================================== */

document.addEventListener('DOMContentLoaded', () => {

    /* ==================================================
       Application Database
       لإضافة تطبيق مستقبلًا نضيف بياناته هنا فقط
    ================================================== */

    const applications = [
        {
            id: 'termux',
            name: 'Termux',
            description: 'A powerful terminal environment for Android.',
            longDescription:
                'Termux combines powerful terminal emulation with an extensive Linux package collection for Android.',
            version: '0.118',
            size: '15 MB',
            source: 'F-Droid',
            license: 'GPL-3.0',
            platform: 'Android',
            category: 'Development',
            added: '2026-07-21',
            downloadUrl: 'https://f-droid.org/packages/com.termux/',
            iconType: 'terminal'
        },
        {
            id: 'newpipe',
            name: 'NewPipe',
            description: 'A lightweight and privacy-friendly video player.',
            longDescription:
                'NewPipe is a free and open-source Android video application that works without requiring proprietary Google services.',
            version: '0.28.1',
            size: '12 MB',
            source: 'F-Droid',
            license: 'GPL-3.0',
            platform: 'Android',
            category: 'Media',
            added: '2026-07-22',
            downloadUrl:
                'https://f-droid.org/packages/org.schabi.newpipe/',
            iconType: 'video'
        }
    ];

    /* ==================================================
       Page Elements
    ================================================== */

    const body = document.body;

    const searchInput =
        document.getElementById('app-search');

    const clearSearchButton =
        document.getElementById('clear-search-button');

    const searchResults =
        document.getElementById('search-results');

    const applicationsGrid =
        document.getElementById('applications-grid');

    const applicationCount =
        document.getElementById('application-count');

    const emptyState =
        document.getElementById('empty-state');

    const newestButton =
        document.getElementById('newest-button');

    const themeButton =
        document.getElementById('theme-button');

    const guideButton =
        document.getElementById('guide-button');

    const fdroidInfoButton =
        document.getElementById('fdroid-info-button');

    const applicationModal =
        document.getElementById('application-modal');

    const fdroidModal =
        document.getElementById('fdroid-modal');

    const guideModal =
        document.getElementById('guide-modal');

    const modals = [
        applicationModal,
        fdroidModal,
        guideModal
    ].filter(Boolean);

    let displayedApplications = [...applications];
    let newestFirst = true;

    /* ==================================================
       Application Icons
    ================================================== */

    function getApplicationIcon(application) {

        if (application.iconType === 'terminal') {
            return `
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
                        fill="none"
                        stroke="white"
                        stroke-width="5"
                        stroke-linecap="round"
                    ></path>
                </svg>
            `;
        }

        if (application.iconType === 'video') {
            return `
                <svg viewBox="0 0 64 64" aria-hidden="true">
                    <rect
                        width="64"
                        height="64"
                        rx="15"
                        fill="#e53935"
                    ></rect>

                    <path
                        d="M26 20L45 32L26 44Z"
                        fill="white"
                    ></path>
                </svg>
            `;
        }

        return `
            <svg viewBox="0 0 64 64" aria-hidden="true">
                <rect
                    width="64"
                    height="64"
                    rx="15"
                    fill="#2563eb"
                ></rect>

                <text
                    x="32"
                    y="40"
                    text-anchor="middle"
                    fill="white"
                    font-size="26"
                    font-weight="700"
                    font-family="Arial, sans-serif"
                >
                    ${escapeHtml(application.name.charAt(0))}
                </text>
            </svg>
        `;
    }

    /* ==================================================
       Render Applications
    ================================================== */

    function renderApplications(applicationList) {
        if (!applicationsGrid) {
            return;
        }

        applicationsGrid.innerHTML = '';

        applicationList.forEach(application => {
            applicationsGrid.appendChild(
                createApplicationCard(application)
            );
        });

        updateApplicationCount(applicationList.length);

        applicationsGrid.hidden =
            applicationList.length === 0;

        if (emptyState) {
            emptyState.hidden =
                applicationList.length !== 0;
        }
    }

    function createApplicationCard(application) {
        const card = document.createElement('article');

        card.className = 'application-card';
        card.dataset.appId = application.id;
        card.dataset.appName = application.name;
        card.dataset.added = application.added;

        card.innerHTML = `
            <button
                class="application-main"
                type="button"
                aria-label="View ${escapeHtml(application.name)} information"
            >
                <div class="application-icon">
                    ${getApplicationIcon(application)}
                </div>

                <div class="application-summary">
                    <h3>
                        ${escapeHtml(application.name)}
                    </h3>

                    <p>
                        ${escapeHtml(application.description)}
                    </p>

                    <div class="application-meta">
                        <span>
                            ${escapeHtml(application.version)}
                        </span>

                        <span>
                            ${escapeHtml(application.size)}
                        </span>
                    </div>
                </div>
            </button>

            <div class="application-footer">
                <span class="source-label">
                    Source: ${escapeHtml(application.source)}
                </span>

                <button
                    class="download-icon-button"
                    type="button"
                    aria-label="Download ${escapeHtml(application.name)}"
                    title="Download ${escapeHtml(application.name)}"
                >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path
                            d="M12 4V15M7.5 10.5L12 15L16.5 10.5"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="1.9"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                        ></path>

                        <path
                            d="M5 19H19"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="1.9"
                            stroke-linecap="round"
                        ></path>
                    </svg>
                </button>
            </div>
        `;

        const mainButton =
            card.querySelector('.application-main');

        const downloadButton =
            card.querySelector('.download-icon-button');

        mainButton?.addEventListener('click', () => {
            openApplicationModal(application);
        });

        downloadButton?.addEventListener('click', event => {
            event.stopPropagation();
            openApplicationModal(application);
        });

        return card;
    }

    /* ==================================================
       Application Modal
    ================================================== */

    function openApplicationModal(application) {
        if (!applicationModal) {
            return;
        }

        const title =
            applicationModal.querySelector(
                '#application-modal-title'
            );

        const meta =
            applicationModal.querySelector(
                '.modal-app-heading p'
            );

        const icon =
            applicationModal.querySelector(
                '.modal-app-heading .application-icon'
            );

        const description =
            applicationModal.querySelector(
                '.modal-section p'
            );

        const details =
            applicationModal.querySelectorAll(
                '.application-details dd'
            );

        const downloadLink =
            applicationModal.querySelector(
                '.primary-download-button'
            );

        if (title) {
            title.textContent = application.name;
        }

        if (meta) {
            meta.textContent =
                `Version ${application.version} · ${application.size}`;
        }

        if (icon) {
            icon.innerHTML =
                getApplicationIcon(application);
        }

        if (description) {
            description.textContent =
                application.longDescription;
        }

        if (details[0]) {
            details[0].textContent =
                application.source;
        }

        if (details[1]) {
            details[1].textContent =
                application.license;
        }

        if (details[2]) {
            details[2].textContent =
                application.platform;
        }

        if (downloadLink) {
            downloadLink.href =
                application.downloadUrl;

            downloadLink.textContent =
                `Download ${application.name} from ${application.source}`;
        }

        openModal(applicationModal);
    }

    /* ==================================================
       Search
    ================================================== */

    searchInput?.addEventListener('input', () => {
        const query =
            normalizeText(searchInput.value);

        if (clearSearchButton) {
            clearSearchButton.hidden =
                query.length === 0;
        }

        displayedApplications =
            applications.filter(application => {
                const searchableContent =
                    normalizeText(`
                        ${application.name}
                        ${application.description}
                        ${application.longDescription}
                        ${application.category}
                        ${application.source}
                    `);

                return searchableContent.includes(query);
            });

        renderApplications(displayedApplications);
        renderSearchSuggestions(query);
    });

    clearSearchButton?.addEventListener('click', () => {
        if (!searchInput) {
            return;
        }

        searchInput.value = '';

        if (clearSearchButton) {
            clearSearchButton.hidden = true;
        }

        if (searchResults) {
            searchResults.hidden = true;
            searchResults.innerHTML = '';
        }

        displayedApplications = [...applications];

        renderApplications(displayedApplications);
        searchInput.focus();
    });

    function renderSearchSuggestions(query) {
        if (!searchResults) {
            return;
        }

        searchResults.innerHTML = '';

        if (!query) {
            searchResults.hidden = true;
            return;
        }

        const suggestions =
            applications.filter(application =>
                normalizeText(application.name)
                    .includes(query)
            );

        if (suggestions.length === 0) {
            searchResults.hidden = true;
            return;
        }

        suggestions
            .slice(0, 5)
            .forEach(application => {
                const suggestion =
                    document.createElement('button');

                suggestion.type = 'button';
                suggestion.className =
                    'search-result-item';

                suggestion.innerHTML = `
                    <div class="search-result-icon">
                        ${getApplicationIcon(application)}
                    </div>

                    <div class="search-result-text">
                        <strong>
                            ${escapeHtml(application.name)}
                        </strong>

                        <span>
                            ${escapeHtml(application.category)}
                        </span>
                    </div>
                `;

                suggestion.addEventListener('click', () => {
                    if (searchInput) {
                        searchInput.value =
                            application.name;
                    }

                    if (clearSearchButton) {
                        clearSearchButton.hidden = false;
                    }

                    searchResults.hidden = true;

                    displayedApplications = [application];

                    renderApplications(
                        displayedApplications
                    );

                    window.setTimeout(() => {
                        openApplicationModal(application);
                    }, 150);
                });

                searchResults.appendChild(suggestion);
            });

        searchResults.hidden = false;
    }

    /* ==================================================
       Newest Sorting
    ================================================== */

    newestButton?.addEventListener('click', () => {
        displayedApplications.sort(
            (firstApplication, secondApplication) => {
                const firstDate =
                    new Date(
                        firstApplication.added
                    ).getTime();

                const secondDate =
                    new Date(
                        secondApplication.added
                    ).getTime();

                return newestFirst
                    ? secondDate - firstDate
                    : firstDate - secondDate;
            }
        );

        newestFirst = !newestFirst;

        renderApplications(displayedApplications);

        newestButton.setAttribute(
            'aria-label',
            newestFirst
                ? 'Sort newest first'
                : 'Sort oldest first'
        );
    });

    /* ==================================================
       Dark Mode
    ================================================== */

    const savedTheme =
        localStorage.getItem('osguide-theme');

    const systemUsesDarkMode =
        window.matchMedia(
            '(prefers-color-scheme: dark)'
        ).matches;

    if (
        savedTheme === 'dark' ||
        (!savedTheme && systemUsesDarkMode)
    ) {
        body.classList.add('dark-mode');
    }

    updateThemeButton();

    themeButton?.addEventListener('click', () => {
        body.classList.toggle('dark-mode');

        const selectedTheme =
            body.classList.contains('dark-mode')
                ? 'dark'
                : 'light';

        localStorage.setItem(
            'osguide-theme',
            selectedTheme
        );

        updateThemeButton();
    });

    function updateThemeButton() {
        if (!themeButton) {
            return;
        }

        const darkModeEnabled =
            body.classList.contains('dark-mode');

        const label = darkModeEnabled
            ? 'Switch to light mode'
            : 'Switch to dark mode';

        themeButton.setAttribute(
            'aria-label',
            label
        );

        themeButton.setAttribute(
            'title',
            label
        );
    }

    /* ==================================================
       Modal System
    ================================================== */

    function openModal(modal) {
        if (!modal) {
            return;
        }

        closeAllModals();

        modal.hidden = false;
        body.classList.add('modal-open');

        const focusableElement =
            modal.querySelector(
                'button, a, input'
            );

        window.setTimeout(() => {
            focusableElement?.focus();
        }, 50);
    }

    function closeModal(modal) {
        if (!modal) {
            return;
        }

        modal.hidden = true;

        const modalStillOpen =
            modals.some(
                currentModal =>
                    currentModal.hidden === false
            );

        if (!modalStillOpen) {
            body.classList.remove('modal-open');
        }
    }

    function closeAllModals() {
        modals.forEach(modal => {
            modal.hidden = true;
        });

        body.classList.remove('modal-open');
    }

    document
        .querySelectorAll('[data-close-modal]')
        .forEach(button => {
            button.addEventListener('click', () => {
                closeModal(
                    button.closest('.modal')
                );
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

    /* ==================================================
       Guide Login Buttons
    ================================================== */

    document
        .querySelectorAll('.login-option')
        .forEach(button => {
            button.addEventListener('click', () => {
                const originalText =
                    button.textContent.trim();

                button.disabled = true;

                button.textContent =
                    'Coming in the authentication stage';

                window.setTimeout(() => {
                    button.disabled = false;
                    button.textContent =
                        originalText;
                }, 1800);
            });
        });

    /* ==================================================
       Utilities
    ================================================== */

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

/* ==========================================
   Initial Rendering
========================================== */

renderApplications(displayedApplications);
});
