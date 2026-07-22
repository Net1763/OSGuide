'use strict';

/* =========================================================
   OSGuide — Main JavaScript File
   Part 1/8
========================================================= */

document.addEventListener('DOMContentLoaded', async () => {
    const SUPABASE_URL = 'https://rqvicenfdzlleureteis.supabase.co';
    const SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_U64um_oKyNG0zXHQu6PuTg_lR9rSIwA';

    const supabaseClient = window.supabase.createClient(
        SUPABASE_URL,
        SUPABASE_PUBLISHABLE_KEY
    );

    /* =============================
       1. Applications Database

    /* =====================================================
       1. Applications Database
    ===================================================== */

    const applications = [
        {
            id: 'termux',
            name: 'Termux',
            description:
                'A powerful terminal environment for Android.',
            longDescription:
                'Termux combines powerful terminal emulation with an extensive Linux package collection for Android.',
            version: '0.118',
            size: '15 MB',
            source: 'F-Droid',
            license: 'GPL-3.0',
            platform: 'Android',
            category: 'Development',
            added: '2026-07-21',
            downloadUrl:
                'https://f-droid.org/packages/com.termux/',
            iconType: 'terminal'
        },

        {
            id: 'newpipe',
            name: 'NewPipe',
            description:
                'A lightweight and privacy-friendly video player.',
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

    /* =====================================================
       2. Page Elements
    ===================================================== */

    const body =
        document.body;

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

    /* =====================================================
       3. Global State
    ===================================================== */

    let displayedApplications =
        [...applications];

    let newestFirst =
        true;

    let lastFocusedElement =
        null;    /* =====================================================
       4. Utility Functions
    ===================================================== */

    function normalizeText(value) {
        return String(value || '')
            .trim()
            .toLowerCase();
    }

    function escapeHTML(value) {
        return String(value || '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    function getApplicationById(applicationId) {
        return applications.find(
            application => application.id === applicationId
        );
    }

    function formatApplicationCount(count) {
        if (count === 1) {
            return '1 application';
        }

        return `${count} applications`;
    }

    function updateApplicationCount(count) {
        if (!applicationCount) {
            return;
        }

        applicationCount.textContent =
            formatApplicationCount(count);
    }

    function showElement(element) {
        if (!element) {
            return;
        }

        element.hidden = false;
    }

    function hideElement(element) {
        if (!element) {
            return;
        }

        element.hidden = true;
    }

    /* =====================================================
       5. Application Icons
    ===================================================== */

    function createTerminalIcon() {
        return `
            <div class="application-icon termux-icon">
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
        `;
    }

    function createVideoIcon() {
        return `
            <div class="application-icon newpipe-icon">
                <svg viewBox="0 0 64 64" aria-hidden="true">
                    <rect
                        width="64"
                        height="64"
                        rx="15"
                        fill="#d32f2f"
                    ></rect>

                    <path
                        d="M26 20L46 32L26 44Z"
                        fill="white"
                    ></path>
                </svg>
            </div>
        `;
    }

    function createApplicationIcon(iconType) {
        switch (iconType) {
            case 'video':
                return createVideoIcon();

            case 'terminal':
            default:
                return createTerminalIcon();
        }
    }

    /* =====================================================
       6. Application Card Template
    ===================================================== */

    function createApplicationCard(application) {
        const safeId =
            escapeHTML(application.id);

        const safeName =
            escapeHTML(application.name);

        const safeDescription =
            escapeHTML(application.description);

        const safeVersion =
            escapeHTML(application.version);

        const safeSize =
            escapeHTML(application.size);

        const safeSource =
            escapeHTML(application.source);

        const safeAdded =
            escapeHTML(application.added);

        return `
            <article
                class="application-card"
                data-app-name="${safeName}"
                data-added="${safeAdded}"
            >
                <button
                    class="application-main"
                    type="button"
                    data-open-app="${safeId}"
                    aria-label="View ${safeName} information"
                >
                    ${createApplicationIcon(application.iconType)}

                    <div class="application-summary">
                        <h3>${safeName}</h3>

                        <p>${safeDescription}</p>

                        <div class="application-meta">
                            <span>${safeVersion}</span>
                            <span>${safeSize}</span>
                        </div>
                    </div>
                </button>

                <div class="application-footer">
                    <span class="source-label">
                        Source: ${safeSource}
                    </span>

                    <button
                        class="download-icon-button"
                        type="button"
                        data-download-app="${safeId}"
                        aria-label="Download ${safeName}"
                        title="Download ${safeName}"
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
                                stroke="currentColor"
                                stroke-width="1.9"
                                stroke-linecap="round"
                            ></path>
                        </svg>
                    </button>
                </div>
            </article>
        `;
    }    /* =====================================================
       7. Render Applications
    ===================================================== */

    function renderApplications(applicationList) {
        if (!applicationsGrid) {
            return;
        }

        applicationsGrid.innerHTML =
            applicationList
                .map(createApplicationCard)
                .join('');

        updateApplicationCount(applicationList.length);

        if (applicationList.length === 0) {
            hideElement(applicationsGrid);
            showElement(emptyState);
        } else {
            showElement(applicationsGrid);
            hideElement(emptyState);
        }

        attachApplicationCardEvents();
    }

    function attachApplicationCardEvents() {
        const openApplicationButtons =
            document.querySelectorAll('[data-open-app]');

        const downloadApplicationButtons =
            document.querySelectorAll('[data-download-app]');

        openApplicationButtons.forEach(button => {
            button.addEventListener('click', () => {
                const applicationId =
                    button.dataset.openApp;

                openApplicationModal(applicationId);
            });
        });

        downloadApplicationButtons.forEach(button => {
            button.addEventListener('click', event => {
                event.stopPropagation();

                const applicationId =
                    button.dataset.downloadApp;

                openApplicationModal(applicationId);
            });
        });
    }

    /* =====================================================
       8. Search System
    ===================================================== */

    function filterApplications(searchValue) {
        const normalizedSearch =
            normalizeText(searchValue);

        if (!normalizedSearch) {
            return [...applications];
        }

        return applications.filter(application => {
            const searchableContent = [
                application.name,
                application.description,
                application.longDescription,
                application.category,
                application.source,
                application.platform
            ]
                .map(normalizeText)
                .join(' ');

            return searchableContent.includes(
                normalizedSearch
            );
        });
    }

    function sortApplications(applicationList) {
        return [...applicationList].sort(
            (firstApplication, secondApplication) => {
                const firstDate =
                    new Date(firstApplication.added).getTime();

                const secondDate =
                    new Date(secondApplication.added).getTime();

                if (newestFirst) {
                    return secondDate - firstDate;
                }

                return firstDate - secondDate;
            }
        );
    }

    function updateDisplayedApplications() {
        const searchValue =
            searchInput ? searchInput.value : '';

        const filteredApplications =
            filterApplications(searchValue);

        displayedApplications =
            sortApplications(filteredApplications);

        renderApplications(displayedApplications);

        updateSearchSuggestions(
            searchValue,
            displayedApplications
        );
    }

    function updateClearSearchButton() {
        if (!searchInput || !clearSearchButton) {
            return;
        }

        const hasSearchValue =
            searchInput.value.trim().length > 0;

        clearSearchButton.hidden =
            !hasSearchValue;
    }

    function clearSearch() {
        if (!searchInput) {
            return;
        }

        searchInput.value = '';

        updateClearSearchButton();
        hideSearchSuggestions();
        updateDisplayedApplications();

        searchInput.focus();
    }

    /* =====================================================
       9. Search Suggestions
    ===================================================== */

    function createSearchSuggestion(application) {
        const safeId =
            escapeHTML(application.id);

        const safeName =
            escapeHTML(application.name);

        const safeDescription =
            escapeHTML(application.description);

        return `
            <button
                class="search-result-item"
                type="button"
                data-search-app="${safeId}"
            >
                ${createApplicationIcon(application.iconType)}

                <span class="search-result-content">
                    <strong>${safeName}</strong>
                    <small>${safeDescription}</small>
                </span>
            </button>
        `;
    }

    function updateSearchSuggestions(
        searchValue,
        matchingApplications
    ) {
        if (!searchResults) {
            return;
        }

        const normalizedSearch =
            normalizeText(searchValue);

        if (!normalizedSearch) {
            hideSearchSuggestions();
            return;
        }

        const suggestions =
            matchingApplications.slice(0, 5);

        if (suggestions.length === 0) {
            searchResults.innerHTML = `
                <div class="search-result-message">
                    No matching applications
                </div>
            `;

            showElement(searchResults);
            return;
        }

        searchResults.innerHTML =
            suggestions
                .map(createSearchSuggestion)
                .join('');

        showElement(searchResults);

        attachSearchSuggestionEvents();
    }

    function attachSearchSuggestionEvents() {
        const suggestionButtons =
            document.querySelectorAll('[data-search-app]');

        suggestionButtons.forEach(button => {
            button.addEventListener('click', () => {
                const applicationId =
                    button.dataset.searchApp;

                const application =
                    getApplicationById(applicationId);

                if (!application) {
                    return;
                }

                if (searchInput) {
                    searchInput.value =
                        application.name;
                }

                updateClearSearchButton();
                hideSearchSuggestions();
                updateDisplayedApplications();
                openApplicationModal(applicationId);
            });
        });
    }

    function hideSearchSuggestions() {
        if (!searchResults) {
            return;
        }

        searchResults.innerHTML = '';
        hideElement(searchResults);
    }

    /* =====================================================
       10. Search Event Listeners
    ===================================================== */

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            updateClearSearchButton();
            updateDisplayedApplications();
        });

        searchInput.addEventListener('focus', () => {
            const searchValue =
                searchInput.value.trim();

            if (searchValue) {
                updateSearchSuggestions(
                    searchValue,
                    displayedApplications
                );
            }
        });

        searchInput.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                hideSearchSuggestions();
                searchInput.blur();
            }
        });
    }

    if (clearSearchButton) {
        clearSearchButton.addEventListener(
            'click',
            clearSearch
        );
    }

    document.addEventListener('click', event => {
        const clickedInsideSearch =
            event.target.closest('.search-container');

        const clickedInsideResults =
            event.target.closest('#search-results');

        if (
            !clickedInsideSearch &&
            !clickedInsideResults
        ) {
            hideSearchSuggestions();
        }
    });

    /* =====================================================
       11. Newest Sorting
    ===================================================== */

    function updateSortButtonState() {
        if (!newestButton) {
            return;
        }

        const label =
            newestButton.querySelector('span');

        newestButton.classList.toggle(
            'is-active',
            newestFirst
        );

        newestButton.setAttribute(
            'aria-pressed',
            String(newestFirst)
        );

        if (label) {
            label.textContent =
                newestFirst
                    ? 'Newest'
                    : 'Oldest';
        }
    }

    if (newestButton) {
        newestButton.addEventListener('click', () => {
            newestFirst =
                !newestFirst;

            updateSortButtonState();
            updateDisplayedApplications();
        });
    }    /* =====================================================
       12. Theme System
    ===================================================== */

    function applyTheme(theme) {
        const useDarkTheme =
            theme === 'dark';

        body.classList.toggle(
            'dark-theme',
            useDarkTheme
        );

        body.classList.toggle(
            'light-theme',
            !useDarkTheme
        );

        if (themeButton) {
            themeButton.setAttribute(
                'aria-pressed',
                String(useDarkTheme)
            );

            themeButton.setAttribute(
                'title',
                useDarkTheme
                    ? 'Switch to light mode'
                    : 'Switch to dark mode'
            );

            themeButton.setAttribute(
                'aria-label',
                useDarkTheme
                    ? 'Switch to light mode'
                    : 'Switch to dark mode'
            );
        }

        try {
            localStorage.setItem(
                'osguide-theme',
                theme
            );
        } catch (error) {
            console.warn(
                'OSGuide could not save the theme.',
                error
            );
        }
    }

    function getSavedTheme() {
        try {
            const savedTheme =
                localStorage.getItem('osguide-theme');

            if (
                savedTheme === 'dark' ||
                savedTheme === 'light'
            ) {
                return savedTheme;
            }
        } catch (error) {
            console.warn(
                'OSGuide could not read the saved theme.',
                error
            );
        }

        const prefersDarkTheme =
            window.matchMedia &&
            window.matchMedia(
                '(prefers-color-scheme: dark)'
            ).matches;

        return prefersDarkTheme
            ? 'dark'
            : 'light';
    }

    function toggleTheme() {
        const darkThemeIsActive =
            body.classList.contains('dark-theme');

        applyTheme(
            darkThemeIsActive
                ? 'light'
                : 'dark'
        );
    }

    if (themeButton) {
        themeButton.addEventListener(
            'click',
            toggleTheme
        );
    }

    /* =====================================================
       13. General Modal System
    ===================================================== */

    function getFocusableElements(modal) {
        if (!modal) {
            return [];
        }

        return Array.from(
            modal.querySelectorAll(
                [
                    'a[href]',
                    'button:not([disabled])',
                    'input:not([disabled])',
                    'select:not([disabled])',
                    'textarea:not([disabled])',
                    '[tabindex]:not([tabindex="-1"])'
                ].join(',')
            )
        ).filter(element => {
            return !element.hidden;
        });
    }

    function openModal(modal) {
        if (!modal) {
            return;
        }

        lastFocusedElement =
            document.activeElement;

        modals.forEach(currentModal => {
            if (currentModal !== modal) {
                currentModal.hidden = true;
                currentModal.classList.remove('is-open');
            }
        });

        modal.hidden = false;

        requestAnimationFrame(() => {
            modal.classList.add('is-open');
        });

        body.classList.add('modal-open');

        const focusableElements =
            getFocusableElements(modal);

        if (focusableElements.length > 0) {
            focusableElements[0].focus();
        }
    }

    function closeModal(modal) {
        if (!modal) {
            return;
        }

        modal.classList.remove('is-open');
        modal.hidden = true;

        const anotherModalIsOpen =
            modals.some(currentModal => {
                return !currentModal.hidden;
            });

        if (!anotherModalIsOpen) {
            body.classList.remove('modal-open');
        }

        if (
            lastFocusedElement &&
            typeof lastFocusedElement.focus === 'function'
        ) {
            lastFocusedElement.focus();
        }

        lastFocusedElement = null;
    }

    function closeAllModals() {
        modals.forEach(modal => {
            modal.classList.remove('is-open');
            modal.hidden = true;
        });

        body.classList.remove('modal-open');

        if (
            lastFocusedElement &&
            typeof lastFocusedElement.focus === 'function'
        ) {
            lastFocusedElement.focus();
        }

        lastFocusedElement = null;
    }

    function getOpenModal() {
        return modals.find(modal => {
            return modal && !modal.hidden;
        });
    }

    function trapModalFocus(event, modal) {
        if (
            event.key !== 'Tab' ||
            !modal
        ) {
            return;
        }

        const focusableElements =
            getFocusableElements(modal);

        if (focusableElements.length === 0) {
            event.preventDefault();
            return;
        }

        const firstElement =
            focusableElements[0];

        const lastElement =
            focusableElements[
                focusableElements.length - 1
            ];

        if (
            event.shiftKey &&
            document.activeElement === firstElement
        ) {
            event.preventDefault();
            lastElement.focus();
            return;
        }

        if (
            !event.shiftKey &&
            document.activeElement === lastElement
        ) {
            event.preventDefault();
            firstElement.focus();
        }
    }

    document.addEventListener('keydown', event => {
        const openModalElement =
            getOpenModal();

        if (!openModalElement) {
            return;
        }

        if (event.key === 'Escape') {
            event.preventDefault();
            closeModal(openModalElement);
            return;
        }

        trapModalFocus(
            event,
            openModalElement
        );
    });

    document.addEventListener('click', event => {
        const closeButton =
            event.target.closest('[data-close-modal]');

        if (!closeButton) {
            return;
        }

        const modal =
            closeButton.closest('.modal');

        closeModal(modal);
    });

    /* =====================================================
       14. Application Modal
    ===================================================== */

    function createApplicationModalIcon(application) {
        return createApplicationIcon(
            application.iconType
        );
    }

    function updateApplicationModal(application) {
        if (
            !applicationModal ||
            !application
        ) {
            return;
        }

        const modalPanel =
            applicationModal.querySelector(
                '.modal-panel'
            );

        if (!modalPanel) {
            return;
        }

        const safeName =
            escapeHTML(application.name);

        const safeVersion =
            escapeHTML(application.version);

        const safeSize =
            escapeHTML(application.size);

        const safeDescription =
            escapeHTML(application.longDescription);

        const safeSource =
            escapeHTML(application.source);

        const safeLicense =
            escapeHTML(application.license);

        const safePlatform =
            escapeHTML(application.platform);

        const safeDownloadUrl =
            escapeHTML(application.downloadUrl);

        modalPanel.innerHTML = `
            <button
                class="modal-close-button"
                type="button"
                data-close-modal
                aria-label="Close application information"
            >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path
                        d="M7 7L17 17M17 7L7 17"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.8"
                        stroke-linecap="round"
                    ></path>
                </svg>
            </button>

            <div class="modal-app-heading">
                ${createApplicationModalIcon(application)}

                <div>
                    <h2 id="application-modal-title">
                        ${safeName}
                    </h2>

                    <p>
                        Version ${safeVersion} · ${safeSize}
                    </p>
                </div>
            </div>

            <div class="modal-section">
                <h3>About this application</h3>

                <p>${safeDescription}</p>
            </div>

            <dl class="application-details">
                <div>
                    <dt>Source</dt>
                    <dd>${safeSource}</dd>
                </div>

                <div>
                    <dt>License</dt>
                    <dd>${safeLicense}</dd>
                </div>

                <div>
                    <dt>Platform</dt>
                    <dd>${safePlatform}</dd>
                </div>
            </dl>

            <a
                class="primary-download-button"
                href="${safeDownloadUrl}"
                target="_blank"
                rel="noopener noreferrer"
            >
                Download from ${safeSource}
            </a>
        `;
    }

    function openApplicationModal(applicationId) {
        const application =
            getApplicationById(applicationId);

        if (!application) {
            console.warn(
                `Application not found: ${applicationId}`
            );
            return;
        }

        updateApplicationModal(application);
        openModal(applicationModal);
    }    /* =====================================================
       15. F-Droid Modal
    ===================================================== */

    if (fdroidInfoButton) {
        fdroidInfoButton.addEventListener('click', () => {
            openModal(fdroidModal);
        });
    }

    /* =====================================================
       16. Guide Modal
    ===================================================== */

    if (guideButton) {
        guideButton.addEventListener('click', () => {
            openModal(guideModal);
        });
    }

    function showLoginMessage(providerName) {
        const provider =
            String(providerName || 'selected method');

        alert(
            `${provider} authentication will be connected in a later development stage.`
        );
    }

    function attachGuideLoginEvents() {
        if (!guideModal) {
            return;
        }

        const loginButtons =
            guideModal.querySelectorAll('.login-option');

        loginButtons.forEach(button => {
            button.addEventListener('click', () => {
                const providerName =
                    button.textContent.trim();

                showLoginMessage(providerName);
            });
        });
    }

    /* =====================================================
       17. Direct Download Handling
    ===================================================== */

    function openDownloadPage(applicationId) {
        const application =
            getApplicationById(applicationId);

        if (!application) {
            console.warn(
                `Download application not found: ${applicationId}`
            );
            return;
        }

        const downloadUrl =
            application.downloadUrl;

        if (!downloadUrl) {
            openApplicationModal(applicationId);
            return;
        }

        window.open(
            downloadUrl,
            '_blank',
            'noopener,noreferrer'
        );
    }

    function attachDirectDownloadEvents() {
        if (!applicationsGrid) {
            return;
        }

        applicationsGrid.addEventListener(
            'click',
            event => {
                const downloadButton =
                    event.target.closest(
                        '[data-download-app]'
                    );

                if (!downloadButton) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();

                const applicationId =
                    downloadButton.dataset.downloadApp;

                openDownloadPage(applicationId);
            }
        );
    }

    /* =====================================================
       18. Keyboard Support
    ===================================================== */

    function focusFirstSearchSuggestion() {
        if (
            !searchResults ||
            searchResults.hidden
        ) {
            return;
        }

        const firstSuggestion =
            searchResults.querySelector(
                '[data-search-app]'
            );

        if (firstSuggestion) {
            firstSuggestion.focus();
        }
    }

    function focusNextSearchSuggestion(
        currentElement,
        direction
    ) {
        if (!searchResults) {
            return;
        }

        const suggestions =
            Array.from(
                searchResults.querySelectorAll(
                    '[data-search-app]'
                )
            );

        if (suggestions.length === 0) {
            return;
        }

        const currentIndex =
            suggestions.indexOf(currentElement);

        if (currentIndex === -1) {
            suggestions[0].focus();
            return;
        }

        const nextIndex =
            (
                currentIndex +
                direction +
                suggestions.length
            ) % suggestions.length;

        suggestions[nextIndex].focus();
    }

    if (searchInput) {
        searchInput.addEventListener(
            'keydown',
            event => {
                if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    focusFirstSearchSuggestion();
                }
            }
        );
    }

    if (searchResults) {
        searchResults.addEventListener(
            'keydown',
            event => {
                const currentSuggestion =
                    event.target.closest(
                        '[data-search-app]'
                    );

                if (!currentSuggestion) {
                    return;
                }

                if (event.key === 'ArrowDown') {
                    event.preventDefault();

                    focusNextSearchSuggestion(
                        currentSuggestion,
                        1
                    );
                }

                if (event.key === 'ArrowUp') {
                    event.preventDefault();

                    focusNextSearchSuggestion(
                        currentSuggestion,
                        -1
                    );
                }

                if (event.key === 'Escape') {
                    event.preventDefault();

                    hideSearchSuggestions();

                    if (searchInput) {
                        searchInput.focus();
                    }
                }
            }
        );
    }

    /* =====================================================
       19. Accessibility Helpers
    ===================================================== */

    function announceApplicationCount(count) {
        if (!applicationCount) {
            return;
        }

        applicationCount.setAttribute(
            'aria-live',
            'polite'
        );

        applicationCount.textContent =
            formatApplicationCount(count);
    }

    function updateApplicationCount(count) {
        announceApplicationCount(count);
    }

    function updateExpandedStates() {
        if (fdroidInfoButton) {
            fdroidInfoButton.setAttribute(
                'aria-expanded',
                String(
                    fdroidModal &&
                    !fdroidModal.hidden
                )
            );
        }

        if (guideButton) {
            guideButton.setAttribute(
                'aria-expanded',
                String(
                    guideModal &&
                    !guideModal.hidden
                )
            );
        }
    }

    const originalOpenModal =
        openModal;

    openModal = function (modal) {
        originalOpenModal(modal);
        updateExpandedStates();
    };

    const originalCloseModal =
        closeModal;

    closeModal = function (modal) {
        originalCloseModal(modal);
        updateExpandedStates();
    };

    /* =====================================================
       20. URL Search Parameter
    ===================================================== */

    function applySearchFromUrl() {
        if (!searchInput) {
            return;
        }

        const parameters =
            new URLSearchParams(
                window.location.search
            );

        const searchValue =
            parameters.get('search');

        if (!searchValue) {
            return;
        }

        searchInput.value =
            searchValue;

        updateClearSearchButton();
    }

    function updateUrlSearchParameter() {
        if (!searchInput) {
            return;
        }

        const currentUrl =
            new URL(window.location.href);

        const searchValue =
            searchInput.value.trim();

        if (searchValue) {
            currentUrl.searchParams.set(
                'search',
                searchValue
            );
        } else {
            currentUrl.searchParams.delete(
                'search'
            );
        }

        window.history.replaceState(
            {},
            '',
            currentUrl
        );
    }

    if (searchInput) {
        searchInput.addEventListener(
            'input',
            updateUrlSearchParameter
        );
    }    /* =====================================================
       21. Correct Application Card Events
    ===================================================== */

    attachApplicationCardEvents = function () {
        const openApplicationButtons =
            document.querySelectorAll('[data-open-app]');

        const downloadApplicationButtons =
            document.querySelectorAll('[data-download-app]');

        openApplicationButtons.forEach(button => {
            button.addEventListener('click', () => {
                const applicationId =
                    button.dataset.openApp;

                openApplicationModal(applicationId);
            });
        });

        downloadApplicationButtons.forEach(button => {
            button.addEventListener('click', event => {
                event.preventDefault();
                event.stopPropagation();

                const applicationId =
                    button.dataset.downloadApp;

                openDownloadPage(applicationId);
            });
        });
    };

    /* =====================================================
       22. Application Data Validation
    ===================================================== */

    function validateApplication(application) {
        if (
            !application ||
            typeof application !== 'object'
        ) {
            return false;
        }

        const requiredProperties = [
            'id',
            'name',
            'description',
            'longDescription',
            'version',
            'size',
            'source',
            'license',
            'platform',
            'added',
            'downloadUrl',
            'iconType'
        ];

        return requiredProperties.every(property => {
            const value =
                application[property];

            return (
                typeof value === 'string' &&
                value.trim().length > 0
            );
        });
    }

    function getValidApplications() {
        return applications.filter(application => {
            const isValid =
                validateApplication(application);

            if (!isValid) {
                console.warn(
                    'Invalid OSGuide application data:',
                    application
                );
            }

            return isValid;
        });
    }

    /* =====================================================
       23. Duplicate Application Protection
    ===================================================== */

    function removeDuplicateApplications(
        applicationList
    ) {
        const applicationMap =
            new Map();

        applicationList.forEach(application => {
            const normalizedId =
                normalizeText(application.id);

            if (!normalizedId) {
                return;
            }

            if (applicationMap.has(normalizedId)) {
                console.warn(
                    `Duplicate application ignored: ${application.id}`
                );

                return;
            }

            applicationMap.set(
                normalizedId,
                application
            );
        });

        return Array.from(
            applicationMap.values()
        );
    }

    function prepareApplications() {
        const validApplications =
            getValidApplications();

        return removeDuplicateApplications(
            validApplications
        );
    }

    /* =====================================================
       24. Date Helpers
    ===================================================== */

    function getApplicationTimestamp(application) {
        if (!application) {
            return 0;
        }

        const timestamp =
            Date.parse(application.added);

        if (Number.isNaN(timestamp)) {
            return 0;
        }

        return timestamp;
    }

    function getNewestApplication(
        applicationList
    ) {
        if (
            !Array.isArray(applicationList) ||
            applicationList.length === 0
        ) {
            return null;
        }

        return [...applicationList].sort(
            (firstApplication, secondApplication) => {
                return (
                    getApplicationTimestamp(
                        secondApplication
                    ) -
                    getApplicationTimestamp(
                        firstApplication
                    )
                );
            }
        )[0];
    }

    /* =====================================================
       25. New Application Badge
    ===================================================== */

    function isNewestApplication(application) {
        const newestApplication =
            getNewestApplication(
                prepareApplications()
            );

        if (!newestApplication) {
            return false;
        }

        return (
            newestApplication.id ===
            application.id
        );
    }

    const originalCreateApplicationCard =
        createApplicationCard;

    createApplicationCard = function (application) {
        const cardMarkup =
            originalCreateApplicationCard(
                application
            );

        if (!isNewestApplication(application)) {
            return cardMarkup;
        }

        return cardMarkup.replace(
            '<div class="application-summary">',
            `
                <div class="application-summary">
                    <span class="new-application-badge">
                        New
                    </span>
            `
        );
    };

    /* =====================================================
       26. Search Status
    ===================================================== */

    function updateSearchStatus() {
        if (!searchInput) {
            return;
        }

        const searchValue =
            searchInput.value.trim();

        if (!searchValue) {
            body.classList.remove(
                'search-is-active'
            );

            return;
        }

        body.classList.add(
            'search-is-active'
        );
    }

    if (searchInput) {
        searchInput.addEventListener(
            'input',
            updateSearchStatus
        );
    }

    /* =====================================================
       27. Empty State Reset Button
    ===================================================== */

    function createEmptyStateResetButton() {
        if (!emptyState) {
            return;
        }

        const existingButton =
            emptyState.querySelector(
                '[data-reset-search]'
            );

        if (existingButton) {
            return;
        }

        const resetButton =
            document.createElement('button');

        resetButton.type =
            'button';

        resetButton.className =
            'empty-state-reset-button';

        resetButton.dataset.resetSearch =
            'true';

        resetButton.textContent =
            'Clear search';

        resetButton.addEventListener(
            'click',
            clearSearch
        );

        emptyState.appendChild(
            resetButton
        );
    }

    /* =====================================================
       28. Footer Year
    ===================================================== */

    function updateCopyrightYear() {
        const copyrightElement =
            document.querySelector(
                '.copyright'
            );

        if (!copyrightElement) {
            return;
        }

        const currentYear =
            new Date().getFullYear();

        copyrightElement.textContent =
            `© ${currentYear} OSGuide. All rights reserved.`;
    }

    /* =====================================================
       29. Brand Home Action
    ===================================================== */

    function attachBrandHomeEvent() {
        const brand =
            document.querySelector('.brand');

        if (!brand) {
            return;
        }

        brand.addEventListener('click', event => {
            event.preventDefault();

            clearSearch();
            closeAllModals();

            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    /* =====================================================
       30. External Link Security
    ===================================================== */

    function secureExternalLinks() {
        const externalLinks =
            document.querySelectorAll(
                'a[target="_blank"]'
            );

        externalLinks.forEach(link => {
            const currentRel =
                link.getAttribute('rel') || '';

            const relValues =
                new Set(
                    currentRel
                        .split(/\s+/)
                        .filter(Boolean)
                );

            relValues.add('noopener');
            relValues.add('noreferrer');

            link.setAttribute(
                'rel',
                Array.from(relValues).join(' ')
            );
        });
    }

    /* =====================================================
       31. Online and Offline Status
    ===================================================== */

    function updateConnectionStatus() {
        const isOnline =
            navigator.onLine;

        body.classList.toggle(
            'is-offline',
            !isOnline
        );

        body.classList.toggle(
            'is-online',
            isOnline
        );
    }

    window.addEventListener(
        'online',
        updateConnectionStatus
    );

    window.addEventListener(
        'offline',
        updateConnectionStatus
    );

    /* =====================================================
       32. Prevent Broken Download Actions
    ===================================================== */

    function applicationHasValidDownloadUrl(
        application
    ) {
        if (
            !application ||
            !application.downloadUrl
        ) {
            return false;
        }

        try {
            const downloadUrl =
                new URL(
                    application.downloadUrl,
                    window.location.href
                );

            return (
                downloadUrl.protocol === 'https:' ||
                downloadUrl.protocol === 'http:'
            );
        } catch (error) {
            return false;
        }
    }

    openDownloadPage = function (applicationId) {
        const application =
            getApplicationById(applicationId);

        if (!application) {
            console.warn(
                `Download application not found: ${applicationId}`
            );

            return;
        }

        if (
            !applicationHasValidDownloadUrl(
                application
            )
        ) {
            openApplicationModal(applicationId);
            return;
        }

        const newWindow =
            window.open(
                application.downloadUrl,
                '_blank',
                'noopener,noreferrer'
            );

        if (!newWindow) {
            window.location.href =
                application.downloadUrl;
        }
    };    /* =====================================================
       33. Application URL Parameter
    ===================================================== */

    function getApplicationIdFromUrl() {
        const parameters =
            new URLSearchParams(
                window.location.search
            );

        return parameters.get('app');
    }

    function updateApplicationUrlParameter(
        applicationId
    ) {
        const currentUrl =
            new URL(window.location.href);

        if (applicationId) {
            currentUrl.searchParams.set(
                'app',
                applicationId
            );
        } else {
            currentUrl.searchParams.delete('app');
        }

        window.history.replaceState(
            {},
            '',
            currentUrl
        );
    }

    const originalOpenApplicationModal =
        openApplicationModal;

    openApplicationModal = function (applicationId) {
        const application =
            getApplicationById(applicationId);

        if (!application) {
            console.warn(
                `Application not found: ${applicationId}`
            );

            return;
        }

        originalOpenApplicationModal(
            applicationId
        );

        updateApplicationUrlParameter(
            applicationId
        );
    };

    function openApplicationFromUrl() {
        const applicationId =
            getApplicationIdFromUrl();

        if (!applicationId) {
            return;
        }

        const application =
            getApplicationById(applicationId);

        if (!application) {
            updateApplicationUrlParameter(null);
            return;
        }

        openApplicationModal(applicationId);
    }

    /* =====================================================
       34. Modal URL Synchronization
    ===================================================== */

    const closeModalWithUrlReset =
        closeModal;

    closeModal = function (modal) {
        const isApplicationModal =
            modal === applicationModal;

        closeModalWithUrlReset(modal);

        if (isApplicationModal) {
            updateApplicationUrlParameter(null);
        }
    };

    const closeAllModalsWithUrlReset =
        closeAllModals;

    closeAllModals = function () {
        closeAllModalsWithUrlReset();
        updateApplicationUrlParameter(null);
    };

    /* =====================================================
       35. Lightweight Notification System
    ===================================================== */

    let notificationTimer =
        null;

    function getNotificationContainer() {
        let notificationContainer =
            document.getElementById(
                'osguide-notification'
            );

        if (notificationContainer) {
            return notificationContainer;
        }

        notificationContainer =
            document.createElement('div');

        notificationContainer.id =
            'osguide-notification';

        notificationContainer.className =
            'osguide-notification';

        notificationContainer.hidden =
            true;

        notificationContainer.setAttribute(
            'role',
            'status'
        );

        notificationContainer.setAttribute(
            'aria-live',
            'polite'
        );

        body.appendChild(
            notificationContainer
        );

        return notificationContainer;
    }

    function showNotification(
        message,
        duration = 3000
    ) {
        const notificationContainer =
            getNotificationContainer();

        if (notificationTimer) {
            window.clearTimeout(
                notificationTimer
            );
        }

        notificationContainer.textContent =
            String(message || '');

        notificationContainer.hidden =
            false;

        requestAnimationFrame(() => {
            notificationContainer.classList.add(
                'is-visible'
            );
        });

        notificationTimer =
            window.setTimeout(() => {
                notificationContainer.classList.remove(
                    'is-visible'
                );

                window.setTimeout(() => {
                    notificationContainer.hidden =
                        true;
                }, 200);
            }, duration);
    }

    /* =====================================================
       36. Improved Login Messages
    ===================================================== */

    showLoginMessage = function (providerName) {
        const provider =
            String(
                providerName ||
                'This sign-in method'
            ).replace(
                /^Continue with\s+/i,
                ''
            );

        showNotification(
            `${provider} sign-in will be available in a later development stage.`
        );
    };

    /* =====================================================
       37. Footer Links
    ===================================================== */

    function attachFooterLinkEvents() {
        const footerLinks =
            document.querySelectorAll(
                '.footer-links a'
            );

        footerLinks.forEach(link => {
            link.addEventListener(
                'click',
                event => {
                    const linkName =
                        link.textContent.trim();

                    const href =
                        link.getAttribute('href');

                    if (
                        href &&
                        href !== '#'
                    ) {
                        return;
                    }

                    event.preventDefault();

                    showNotification(
                        `${linkName} page will be added in a later development stage.`
                    );
                }
            );
        });
    }

    /* =====================================================
       38. Network Status Message
    ===================================================== */

    function announceConnectionStatus() {
        updateConnectionStatus();

        if (navigator.onLine) {
            showNotification(
                'Internet connection restored.',
                2500
            );

            return;
        }

        showNotification(
            'You are currently offline.',
            3500
        );
    }

    window.addEventListener(
        'online',
        announceConnectionStatus
    );

    window.addEventListener(
        'offline',
        announceConnectionStatus
    );

    /* =====================================================
       39. Search Input Debounce
    ===================================================== */

    function debounce(
        callback,
        delay = 150
    ) {
        let timerId =
            null;

        return function (...argumentsList) {
            if (timerId) {
                window.clearTimeout(timerId);
            }

            timerId =
                window.setTimeout(() => {
                    callback.apply(
                        this,
                        argumentsList
                    );
                }, delay);
        };
    }

    const updateSearchSuggestionsDebounced =
        debounce(() => {
            if (!searchInput) {
                return;
            }

            const searchValue =
                searchInput.value;

            const filteredApplications =
                filterApplications(searchValue);

            updateSearchSuggestions(
                searchValue,
                sortApplications(
                    filteredApplications
                )
            );
        }, 120);

    if (searchInput) {
        searchInput.addEventListener(
            'input',
            updateSearchSuggestionsDebounced
        );
    }

    /* =====================================================
       40. Page Keyboard Shortcuts
    ===================================================== */

    document.addEventListener(
        'keydown',
        event => {
            const activeElement =
                document.activeElement;

            const isTyping =
                activeElement &&
                (
                    activeElement.tagName === 'INPUT' ||
                    activeElement.tagName === 'TEXTAREA' ||
                    activeElement.isContentEditable
                );

            if (
                event.key === '/' &&
                !isTyping &&
                searchInput
            ) {
                event.preventDefault();
                searchInput.focus();
                return;
            }

            if (
                event.key.toLowerCase() === 'd' &&
                event.altKey
            ) {
                event.preventDefault();
                toggleTheme();
            }
        }
    );

    /* =====================================================
       41. Page Visibility
    ===================================================== */

    function handlePageVisibilityChange() {
        if (
            document.visibilityState !== 'visible'
        ) {
            hideSearchSuggestions();
        }
    }

    document.addEventListener(
        'visibilitychange',
        handlePageVisibilityChange
    );

    /* =====================================================
       42. Responsive Modal Height
    ===================================================== */

    function updateViewportHeight() {
        const viewportHeight =
            window.innerHeight * 0.01;

        document.documentElement.style.setProperty(
            '--osguide-viewport-height',
            `${viewportHeight}px`
        );
    }

    window.addEventListener(
        'resize',
        updateViewportHeight
    );

    window.addEventListener(
        'orientationchange',
        updateViewportHeight
    );

    /* =====================================================
       43. Image and Link Drag Protection
    ===================================================== */

    function preventAccidentalDragging() {
        const draggableElements =
            document.querySelectorAll(
                'svg, .application-icon'
            );

        draggableElements.forEach(element => {
            element.setAttribute(
                'draggable',
                'false'
            );
        });
    }

    /* =====================================================
       44. Application Grid State
    ===================================================== */

    function updateGridState() {
        if (!applicationsGrid) {
            return;
        }

        applicationsGrid.classList.toggle(
            'has-one-application',
            displayedApplications.length === 1
        );

        applicationsGrid.classList.toggle(
            'has-multiple-applications',
            displayedApplications.length > 1
        );
    }

    const renderApplicationsWithGridState =
        renderApplications;

    renderApplications = function (applicationList) {
        renderApplicationsWithGridState(
            applicationList
        );

        updateGridState();
        secureExternalLinks();
        preventAccidentalDragging();
    };

    /* =====================================================
       45. Safe Initialization Error Display
    ===================================================== */

    function showInitializationError(error) {
        console.error(
            'OSGuide initialization error:',
            error
        );

        if (applicationsGrid) {
            applicationsGrid.innerHTML = `
                <div class="search-result-message">
                    OSGuide could not load the applications.
                    Please refresh the page.
                </div>
            `;
        }

        showNotification(
            'OSGuide encountered an error while loading.',
            5000
        );
    }

    /* =====================================================
       46. Browser Back and Forward Support
    ===================================================== */

    window.addEventListener(
        'popstate',
        () => {
            applySearchFromUrl();
            updateDisplayedApplications();

            const applicationId =
                getApplicationIdFromUrl();

            if (applicationId) {
                openApplicationModal(
                    applicationId
                );
            } else if (
                applicationModal &&
                !applicationModal.hidden
            ) {
                closeModal(
                    applicationModal
                );
            }
        }
    );

    /* =====================================================
       47. Prepared Applications
    ===================================================== */
try {
    const { data, error } = await supabaseClient
        .from('applications')
        .select('*')
        .eq('is_published', true)
        .order('added', { ascending: false });

    if (error) {
        throw error;
    }

    if (Array.isArray(data) && data.length > 0) {
        applications.splice(
            0,
            applications.length,
            ...data.map((app) => ({
                id: String(app.id),
                name: app.name || '',
                description: app.description || '',
                longDescription: app.long_description || '',
                version: app.version || '',
                size: app.size || '',
                source: app.source || 'F-Droid',
                license: app.license || '',
                platform: app.platform || 'Android',
                category: app.category || '',
                added: app.added || '',
                downloadUrl: app.download_url || '',
                iconType: app.icon_type || 'default'
            }))
        );
    }
} catch (error) {
    console.warn(
        'Could not load applications from Supabase. Using local applications.',
        error
    );
}
    const preparedApplications =
        prepareApplications();

    if (
        preparedApplications.length !==
        applications.length
    ) {
        console.warn(
            'Some invalid or duplicate applications were removed.'
        );
    }    /* =====================================================
       48. Final Initialization
    ===================================================== */

    function initializeOSGuide() {
        try {
            applications.splice(
                0,
                applications.length,
                ...preparedApplications
            );

            applyTheme(
                getSavedTheme()
            );

            applySearchFromUrl();
            updateClearSearchButton();
            updateSearchStatus();
            updateSortButtonState();
            updateViewportHeight();
            updateConnectionStatus();
            updateExpandedStates();

            createEmptyStateResetButton();
            updateCopyrightYear();
            attachBrandHomeEvent();
            attachGuideLoginEvents();
            attachFooterLinkEvents();

            displayedApplications =
                sortApplications(
                    filterApplications(
                        searchInput
                            ? searchInput.value
                            : ''
                    )
                );

            renderApplications(
                displayedApplications
            );

            secureExternalLinks();
            preventAccidentalDragging();

            openApplicationFromUrl();

            body.classList.add(
                'osguide-ready'
            );

            console.info(
                `OSGuide loaded successfully with ${applications.length} applications.`
            );
        } catch (error) {
            showInitializationError(error);
        }
    }

    /* =====================================================
       49. Start OSGuide
    ===================================================== */

    initializeOSGuide();

});
