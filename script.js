'use strict';

/* ==================================================
   OSGuide — Dynamic Application System
================================================== */

document.addEventListener('DOMContentLoaded', () => {

    /* ==================================================
       Application Database

       لإضافة تطبيق جديد مستقبلًا:
       انسخ كائن التطبيق، ثم غيّر بياناته فقط.
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

    let visibleApplications = [...applications];
    let newestFirst = true;

    /* ==================================================
       Icons
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
                    y="39"
                    text-anchor="middle"
                    fill="white"
                    font-size="25"
                    font-weight="700"
                    font-family="Arial, sans-serif"
                >
                    ${escapeHtml(application.name.charAt(0))}
                </text>
            </svg>
        `;
    }

    /* ==================================================
       Application Rendering
    ================================================== */

    function renderApplications(applicationList) {
        if (!applicationsGrid) {
            return;
        }

        applicationsGrid.innerHTML = '';

        applicationList.forEach(application => {
            const card = createApplicationCard(application);
            applicationsGrid.appendChild(card);
        });

        updateApplicationCount(applicationList.length);

        if (emptyState) {
            emptyState.hidden = applicationList.length !== 0;
        }

        applicationsGrid.hidden = applicationList.length === 0;
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
                    <h3>${escapeHtml(application.name)}</h3>

                    <p>
                        ${escapeHtml(application.description)}
                    </p>

                    <div class="application-meta">
                        <span>${escapeHtml(application.version)}</span>
                        <span>${escapeHtml(application.size)}</span>
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

        const modalTitle =
            applicationModal.querySelector(
                '#application-modal-title'
            );

        const modalMeta =
            applicationModal.querySelector(
                '.modal-app-heading p'
            );

        const modalIcon =
            applicationModal.querySelector(
                '.modal-app-heading .application-icon'
            );

        const modalDescription =
            applicationModal.querySelector(
                '.modal-section p'
            );

        const detailValues =
            applicationModal.querySelectorAll(
                '.application-details dd'
            );

        const downloadLink =
            applicationModal.querySelector(
                '.primary-download-button'
            );

        if (modalTitle) {
            modalTitle.textContent = application.name;
        }

        if (modalMeta) {
            modalMeta.textContent =
                `Version ${application.version} · ${application.size}`;
        }

        if (modalIcon) {
            modalIcon.innerHTML =
                getApplicationIcon(application);
        }

        if (modalDescription) {
            modalDescription.textContent =
                application.longDescription;
        }

        if (detailValues[0]) {
            detailValues[0].textContent =
                application.source;
        }

        if (detailValues[1]) {
            detailValues[1].textContent =
                application.license;
        }

        if (detailValues[2]) {
            detailValues[2].textContent =
                application.platform;
        }

        if (downloadLink) {
            downloadLink.href = application.downloadUrl;
            downloadLink.textContent =
                `Download ${application.name} from ${application.source}`;
        }

        openModal(applicationModal);
    }

    /* ==================================================
       Search System
    ================================================== */

    searchInput?.addEventListener('input', () => {
        const query =
            normalizeText(searchInput.value);

        if (clearSearchButton) {
            clearSearchButton.hidden =
                query.length === 0;
        }

        visibleApplications =
            applications.filter(application => {
                const searchableText = normalizeText(`
                    ${application.name}
                    ${application.description}
                    ${application.category}
                    ${application.source}
                `);

                return searchableText.includes(query);
            });

        renderApplications(visibleApplications);
        renderSearchSuggestions(query);
    });

    clearSearchButton?.addEventListener('click', () => {
        if (!searchInput) {
            return;
        }

        searchInput.value = '';
        clearSearchButton.hidden = true;

        if (searchResults) {
            searchResults.hidden = true;
            searchResults.innerHTML = '';
        }

        visibleApplications = [...applications];
        renderApplications(visibleApplications);

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
            applications.filter(application => {
                return normalizeText(
                    application.name
                ).includes(query);
            });

        if (suggestions.length === 0) {
            searchResults.hidden = true;
            return;
        }

        suggestions.slice(0, 5).forEach(application => {
            const button =
                document.createElement('button');

            button.type = 'button';
            button.className = 'search-result-item';

            button.innerHTML = `
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

            button.addEventListener('click', () => {
                if (searchInput) {
                    searchInput.value =
                        application.name;
                }

                if (clearSearchButton) {
                    clearSearchButton.hidden = false;
                }

                searchResults.hidden = true;

                visibleApplications = [application];
                renderApplications(visibleApplications);

                window.setTimeout(() => {
                    openApplicationModal(application);
                }, 200);
            });

            searchResults.appendChild(button);
        });

        searchResults.hidden = false;
    }

    /* ==================================================
       Newest Sorting
    ================================================== */

    newestButton?.addEventListener('click', () => {
        visibleApplications.sort(
            (firstApplication, secondApplication) => {
                const firstDate =
                    new Date(firstApplication.added).getTime();

                const secondDate =
                    new Date(secondApplication.added).getTime();

                return newestFirst
                    ? secondDate - firstDate
                    : firstDate - secondDate;
            }
        );

        newestFirst = !newestFirst;

        renderApplications(visibleApplications);

        newestButton.setAttribute(
            'aria-label',
            newestFirst
                ? 'Sort newest first'
                : 'Sort oldest first'
        );
    });

    /* ==================================================
       Theme System
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
            modals.some(item => item.hidden === false);

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
       Login Placeholders
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
                    button.textContent = originalText;
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

    /* ==================================================
       Initial Rendering
    ================================================== */

    renderApplications(visibleApplications);
});
