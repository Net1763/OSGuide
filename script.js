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

    /* =====================================================
       1. Applications Database
       Supabase is the only source of application data.
    ===================================================== */

    const applications = [];

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

    const applicationsPager =
        document.getElementById('applications-pager');

    const applicationsViewport =
        document.getElementById('applications-viewport');

    const applicationsPagination =
        document.getElementById('applications-pagination');

    const applicationsPagePrevious =
        document.getElementById('applications-page-previous');

    const applicationsPageNext =
        document.getElementById('applications-page-next');

    const applicationCount =
        document.getElementById('application-count');

    const emptyState =
        document.getElementById('empty-state');

    const newestButton =
        document.getElementById('newest-button');

    const categoryFilter =
        document.getElementById('category-filter');

    const sourceFilter =
        document.getElementById('source-filter');

    const ratingFilter =
        document.getElementById('rating-filter');

    const resetFiltersButton =
        document.getElementById('reset-filters-button');

    const applicationsListViewButton =
        document.getElementById('applications-list-view');

    const applicationsGridViewButton =
        document.getElementById('applications-grid-view');

    const viewAllApplicationsButton =
        document.getElementById('view-all-applications');

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

    const walletSupportModal =
        document.getElementById('wallet-support-modal');

    const whyInfoModal =
        document.getElementById('why-info-modal');

    const whyInfoModalIcon =
        document.getElementById('why-info-modal-icon');

    const whyInfoModalTitle =
        document.getElementById('why-info-modal-title');

    const whyInfoModalDescription =
        document.getElementById('why-info-modal-description');

    const whyInfoModalContent =
        document.getElementById('why-info-modal-content');

    const whyInfoSecondaryButton =
        document.getElementById('why-info-secondary-button');

    const whyInfoSecondaryLabel =
        document.getElementById('why-info-secondary-label');

    const walletCopyButton =
        document.getElementById('wallet-copy-button');

    const menuButton =
        document.getElementById('menu-button');

    const sideNavigationShell =
        document.getElementById('side-navigation-shell');

    const sideNavigation =
        document.getElementById('side-navigation');

    const sideNavigationBackdrop =
        document.getElementById('side-navigation-backdrop');

    const sideNavigationClose =
        document.getElementById('side-navigation-close');

    const accountCard =
        document.getElementById('account-card');

    const featuredSection =
        document.getElementById('featured-section');

    const featuredApplicationCard =
        document.getElementById('featured-application-card');

    const featuredApplicationVisual =
        document.getElementById('featured-application-visual');

    const featuredApplicationName =
        document.getElementById('featured-application-name');

    const featuredApplicationDescription =
        document.getElementById('featured-application-description');

    const featuredApplicationMeta =
        document.getElementById('featured-application-meta');

    const modals = [
        applicationModal,
        fdroidModal,
        guideModal,
        walletSupportModal,
        whyInfoModal
    ].filter(Boolean);

    /* =====================================================
       3. Global State
    ===================================================== */

    let displayedApplications =
        [...applications];

    let newestFirst =
        true;

    let activeCategory = '';
    let activeSource = '';
    let minimumRating = '';
    let browseMode = 'home';
    let applicationViewMode = 'grid';
    let showAllApplicationsExpanded = false;

    let applicationsPageIndex = 0;
    let applicationsPageSize = 6;
    let applicationsPageCount = 1;

    let applicationsPointerId = null;
    let applicationsPointerStartX = 0;
    let applicationsPointerStartY = 0;
    let applicationsPointerLastX = 0;
    let applicationsPointerLastY = 0;
    let applicationsPointerStartTime = 0;
    let applicationsPointerDragging = false;
    let applicationsSuppressClick = false;

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

    function createDefaultIcon() {
        return `
            <div class="application-icon default-icon">
                <svg viewBox="0 0 64 64" aria-hidden="true">
                    <rect
                        width="64"
                        height="64"
                        rx="15"
                        fill="#e2e8f0"
                    ></rect>

                    <path
                        d="M20 32H44M32 20V44"
                        stroke="#64748b"
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

    function createImageIcon(imageUrl, applicationName) {
        const safeImageUrl =
            escapeHTML(imageUrl);

        const safeApplicationName =
            escapeHTML(applicationName || 'Application');

        return `
            <div class="application-icon image-icon">
                <img
                    src="${safeImageUrl}"
                    alt="${safeApplicationName} logo"
                    loading="lazy"
                    decoding="async"
                    referrerpolicy="no-referrer"
                    style="width:100%;height:100%;object-fit:cover;border-radius:inherit;display:block;"
                >
            </div>
        `;
    }

    function createApplicationIcon(
        iconType,
        imageUrl = '',
        applicationName = ''
    ) {
        if (String(imageUrl || '').trim()) {
            return createImageIcon(
                imageUrl,
                applicationName
            );
        }

        switch (iconType) {
            case 'video':
                return createVideoIcon();

            case 'terminal':
                return createTerminalIcon();

            default:
                return createDefaultIcon();
        }
    }


    /* =====================================================
       5B. Directory Card State
    ===================================================== */

    const favoriteApplicationIds = new Set();

    function loadFavoriteApplications() {
        try {
            const savedFavorites =
                JSON.parse(
                    localStorage.getItem('osguide-favorites') || '[]'
                );

            if (!Array.isArray(savedFavorites)) {
                return;
            }

            favoriteApplicationIds.clear();

            savedFavorites.forEach(applicationId => {
                const normalizedId =
                    String(applicationId || '').trim();

                if (normalizedId) {
                    favoriteApplicationIds.add(normalizedId);
                }
            });
        } catch (error) {
            console.warn(
                'OSGuide could not load favorites.',
                error
            );
        }
    }

    function saveFavoriteApplications() {
        try {
            localStorage.setItem(
                'osguide-favorites',
                JSON.stringify(
                    Array.from(favoriteApplicationIds)
                )
            );
        } catch (error) {
            console.warn(
                'OSGuide could not save favorites.',
                error
            );
        }
    }

    function isApplicationFavorite(applicationId) {
        return favoriteApplicationIds.has(
            String(applicationId || '')
        );
    }

    function toggleApplicationFavorite(applicationId) {
        const normalizedId =
            String(applicationId || '').trim();

        if (!normalizedId) {
            return false;
        }

        if (favoriteApplicationIds.has(normalizedId)) {
            favoriteApplicationIds.delete(normalizedId);
        } else {
            favoriteApplicationIds.add(normalizedId);
        }

        saveFavoriteApplications();

        return favoriteApplicationIds.has(normalizedId);
    }

    function getApplicationRating(application) {
        const rating =
            Number(application?.rating);

        if (
            Number.isFinite(rating) &&
            rating > 0 &&
            rating <= 5
        ) {
            return rating;
        }

        return null;
    }

    function getApplicationRatingCount(application) {
        const ratingCount =
            Number(application?.ratingCount);

        if (
            Number.isFinite(ratingCount) &&
            ratingCount > 0
        ) {
            return Math.floor(ratingCount);
        }

        return 0;
    }

    function formatRatingCount(ratingCount) {
        if (ratingCount >= 1000) {
            const compact =
                ratingCount >= 10000
                    ? Math.round(ratingCount / 1000)
                    : Math.round(ratingCount / 100) / 10;

            return `${compact}K`;
        }

        return String(ratingCount);
    }

    function createApplicationRatingMarkup(application) {
        const rating =
            getApplicationRating(application);

        const ratingCount =
            getApplicationRatingCount(application);

        if (!rating) {
            return `
                <div
                    class="application-rating is-unrated"
                    aria-label="This application has not been rated yet"
                >
                    <span class="application-rating-star">★</span>
                    <strong>—</strong>
                    <span>(0)</span>
                </div>
            `;
        }

        return `
            <div
                class="application-rating"
                aria-label="${rating.toFixed(1)} out of 5 from ${ratingCount} ratings"
            >
                <span class="application-rating-star">★</span>
                <strong>${rating.toFixed(1)}</strong>
                <span>(${formatRatingCount(ratingCount)})</span>
            </div>
        `;
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

        const favorite =
            isApplicationFavorite(application.id);

        return `
            <article
                class="application-card"
                data-app-name="${safeName}"
                data-added="${safeAdded}"
                data-application-id="${safeId}"
            >
                <button
                    class="application-favorite-button${favorite ? ' is-favorite' : ''}"
                    type="button"
                    data-favorite-app="${safeId}"
                    aria-label="${favorite ? 'Remove' : 'Add'} ${safeName} ${favorite ? 'from' : 'to'} favorites"
                    aria-pressed="${favorite ? 'true' : 'false'}"
                    title="${favorite ? 'Remove from favorites' : 'Add to favorites'}"
                >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M6 4.5H18V20L12 16.3L6 20V4.5Z"></path>
                    </svg>
                </button>

                <button
                    class="application-main"
                    type="button"
                    data-open-app="${safeId}"
                    aria-label="View ${safeName} information"
                >
                    ${createApplicationIcon(
                        application.iconType,
                        application.imageUrl,
                        application.name
                    )}

                    <div class="application-summary">
                        <h3>${safeName}</h3>

                        <p>${safeDescription}</p>
                    </div>
                </button>

                ${createApplicationRatingMarkup(application)}

                <div class="application-meta">
                    <span>${safeVersion}</span>
                    <span>${safeSize}</span>
                </div>

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

                        <span>Download</span>
                    </button>
                </div>
            </article>
        `;
    }    /* =====================================================
       7. Render Applications
    ===================================================== */

    function getApplicationsPageSize() {
        if (showAllApplicationsExpanded) {
            return Math.max(
                displayedApplications.length,
                1
            );
        }

        const viewportWidth =
            window.innerWidth ||
            document.documentElement.clientWidth ||
            0;

        if (applicationViewMode === 'list') {
            if (viewportWidth >= 980) {
                return 9;
            }

            if (viewportWidth >= 620) {
                return 6;
            }

            return 4;
        }

        if (viewportWidth >= 980) {
            return 9;
        }

        if (viewportWidth >= 620) {
            return 6;
        }

        return 4;
    }

    function clampApplicationsPageIndex() {
        applicationsPageSize =
            getApplicationsPageSize();

        applicationsPageCount =
            Math.max(
                1,
                Math.ceil(
                    displayedApplications.length /
                    applicationsPageSize
                )
            );

        applicationsPageIndex =
            Math.min(
                Math.max(
                    applicationsPageIndex,
                    0
                ),
                applicationsPageCount - 1
            );
    }

    function getApplicationsPages(applicationList) {
        const pages = [];

        for (
            let index = 0;
            index < applicationList.length;
            index += applicationsPageSize
        ) {
            pages.push(
                applicationList.slice(
                    index,
                    index + applicationsPageSize
                )
            );
        }

        return pages;
    }

    function getApplicationsPageElement(pageIndex) {
        if (!applicationsGrid) {
            return null;
        }

        return applicationsGrid.querySelector(
            `[data-applications-page-panel="${pageIndex}"]`
        );
    }

    function updateApplicationsPaginationControls() {
        if (
            !applicationsPagination ||
            !applicationsPager
        ) {
            return;
        }

        const hasMultiplePages =
            applicationsPageCount > 1;

        applicationsPager.classList.toggle(
            'has-multiple-pages',
            hasMultiplePages
        );

        if (applicationsPagePrevious) {
            applicationsPagePrevious.disabled =
                !hasMultiplePages ||
                applicationsPageIndex <= 0;
        }

        if (applicationsPageNext) {
            applicationsPageNext.disabled =
                !hasMultiplePages ||
                applicationsPageIndex >=
                    applicationsPageCount - 1;
        }

        if (!hasMultiplePages) {
            applicationsPagination.innerHTML = '';
            applicationsPagination.hidden = true;
            return;
        }

        applicationsPagination.hidden = false;

        applicationsPagination.innerHTML =
            Array.from(
                { length: applicationsPageCount },
                (_, pageIndex) => {
                    const active =
                        pageIndex ===
                        applicationsPageIndex;

                    return `
                        <button
                            class="applications-page-dot${active ? ' is-active' : ''}"
                            type="button"
                            data-applications-page="${pageIndex}"
                            aria-label="Go to applications page ${pageIndex + 1}"
                            aria-current="${active ? 'page' : 'false'}"
                        ></button>
                    `;
                }
            ).join('');

        applicationsPagination
            .querySelectorAll(
                '[data-applications-page]'
            )
            .forEach(button => {
                button.addEventListener(
                    'click',
                    () => {
                        goToApplicationsPage(
                            Number(
                                button.dataset.applicationsPage
                            )
                        );
                    }
                );
            });
    }

    function getApplicationsViewportWidth() {
        if (!applicationsViewport) {
            return 0;
        }

        return applicationsViewport.clientWidth || 0;
    }

    function setApplicationsTrackPosition(
        dragOffset = 0,
        animate = true
    ) {
        if (
            !applicationsGrid ||
            !applicationsViewport
        ) {
            return;
        }

        const viewportWidth =
            getApplicationsViewportWidth();

        const baseOffset =
            applicationsPageIndex *
            viewportWidth;

        applicationsGrid.classList.toggle(
            'is-dragging',
            !animate
        );

        applicationsGrid.style.transform =
            `translate3d(${baseOffset + dragOffset}px, 0, 0)`;
    }

    function goToApplicationsPage(
        requestedPageIndex,
        options = {}
    ) {
        clampApplicationsPageIndex();

        const nextPageIndex =
            Math.min(
                Math.max(
                    Number(requestedPageIndex) || 0,
                    0
                ),
                applicationsPageCount - 1
            );

        applicationsPageIndex =
            nextPageIndex;

        setApplicationsTrackPosition(
            0,
            options.instant !== true
        );

        updateApplicationsPaginationControls();
    }

    function renderApplications(
        applicationList,
        options = {}
    ) {
        if (!applicationsGrid) {
            return;
        }

        if (!options.preservePage) {
            applicationsPageIndex = 0;
        }

        displayedApplications =
            [...applicationList];

        clampApplicationsPageIndex();

        const pages =
            getApplicationsPages(
                displayedApplications
            );

        applicationsGrid.innerHTML =
            pages
                .map(
                    (pageApplications, pageIndex) => `
                        <section
                            class="applications-page-panel"
                            data-applications-page-panel="${pageIndex}"
                            aria-label="Applications page ${pageIndex + 1}"
                        >
                            <div class="applications-page-grid">
                                ${pageApplications
                                    .map(createApplicationCard)
                                    .join('')}
                            </div>
                        </section>
                    `
                )
                .join('');

        updateApplicationCount(
            displayedApplications.length
        );

        if (
            displayedApplications.length === 0
        ) {
            hideElement(
                applicationsPager ||
                applicationsGrid
            );
            showElement(emptyState);
        } else {
            showElement(
                applicationsPager ||
                applicationsGrid
            );
            hideElement(emptyState);
        }

        updateApplicationsPaginationControls();
        attachApplicationCardEvents();

        requestAnimationFrame(() => {
            goToApplicationsPage(
                applicationsPageIndex,
                {
                    instant: true
                }
            );
        });
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

    function attachApplicationsPagingEvents() {
        if (applicationsPagePrevious) {
            applicationsPagePrevious.addEventListener(
                'click',
                () => {
                    goToApplicationsPage(
                        applicationsPageIndex - 1
                    );
                }
            );
        }

        if (applicationsPageNext) {
            applicationsPageNext.addEventListener(
                'click',
                () => {
                    goToApplicationsPage(
                        applicationsPageIndex + 1
                    );
                }
            );
        }

        if (applicationsViewport) {
            applicationsViewport.addEventListener(
                'pointerdown',
                event => {
                    if (
                        applicationsPageCount <= 1 ||
                        (
                            event.pointerType === 'mouse' &&
                            event.button !== 0
                        )
                    ) {
                        return;
                    }

                    applicationsPointerId =
                        event.pointerId;

                    applicationsPointerStartX =
                        event.clientX;

                    applicationsPointerStartY =
                        event.clientY;

                    applicationsPointerLastX =
                        event.clientX;

                    applicationsPointerLastY =
                        event.clientY;

                    applicationsPointerStartTime =
                        Date.now();

                    applicationsPointerDragging =
                        false;

                    applicationsSuppressClick =
                        false;

                    try {
                        applicationsViewport.setPointerCapture(
                            event.pointerId
                        );
                    } catch (error) {
                        // Pointer capture is optional.
                    }
                }
            );

            applicationsViewport.addEventListener(
                'pointermove',
                event => {
                    if (
                        applicationsPointerId === null ||
                        event.pointerId !==
                            applicationsPointerId
                    ) {
                        return;
                    }

                    applicationsPointerLastX =
                        event.clientX;

                    applicationsPointerLastY =
                        event.clientY;

                    const deltaX =
                        applicationsPointerLastX -
                        applicationsPointerStartX;

                    const deltaY =
                        applicationsPointerLastY -
                        applicationsPointerStartY;

                    if (!applicationsPointerDragging) {
                        if (
                            Math.abs(deltaX) < 8 &&
                            Math.abs(deltaY) < 8
                        ) {
                            return;
                        }

                        if (
                            Math.abs(deltaY) >
                            Math.abs(deltaX)
                        ) {
                            return;
                        }

                        applicationsPointerDragging =
                            true;
                    }

                    if (!applicationsPointerDragging) {
                        return;
                    }

                    event.preventDefault();

                    const atFirstPage =
                        applicationsPageIndex <= 0;

                    const atLastPage =
                        applicationsPageIndex >=
                        applicationsPageCount - 1;

                    /*
                     * Required OSGuide direction:
                     * drag RIGHT -> NEXT page
                     * drag LEFT  -> PREVIOUS page
                     */
                    const pullingPastFirst =
                        atFirstPage &&
                        deltaX < 0;

                    const pullingPastLast =
                        atLastPage &&
                        deltaX > 0;

                    const resistance =
                        (
                            pullingPastFirst ||
                            pullingPastLast
                        )
                            ? 0.24
                            : 1;

                    setApplicationsTrackPosition(
                        deltaX * resistance,
                        false
                    );
                }
            );

            function finishApplicationsPointer(
                event,
                cancelled = false
            ) {
                if (
                    applicationsPointerId === null ||
                    (
                        event &&
                        event.pointerId !==
                            applicationsPointerId
                    )
                ) {
                    return;
                }

                const endX =
                    event && Number.isFinite(event.clientX)
                        ? event.clientX
                        : applicationsPointerLastX;

                const endY =
                    event && Number.isFinite(event.clientY)
                        ? event.clientY
                        : applicationsPointerLastY;

                const deltaX =
                    endX -
                    applicationsPointerStartX;

                const deltaY =
                    endY -
                    applicationsPointerStartY;

                const elapsed =
                    Math.max(
                        Date.now() -
                        applicationsPointerStartTime,
                        1
                    );

                const velocityX =
                    Math.abs(deltaX) /
                    elapsed;

                const horizontalSwipe =
                    !cancelled &&
                    applicationsPointerDragging &&
                    Math.abs(deltaX) >
                        Math.abs(deltaY);

                const shouldChangePage =
                    horizontalSwipe &&
                    (
                        Math.abs(deltaX) >= 52 ||
                        (
                            Math.abs(deltaX) >= 26 &&
                            velocityX >= 0.34
                        )
                    );

                applicationsSuppressClick =
                    horizontalSwipe;

                applicationsPointerId =
                    null;

                applicationsPointerDragging =
                    false;

                if (shouldChangePage) {
                    if (deltaX > 0) {
                        goToApplicationsPage(
                            applicationsPageIndex + 1
                        );
                    } else {
                        goToApplicationsPage(
                            applicationsPageIndex - 1
                        );
                    }
                } else {
                    setApplicationsTrackPosition(
                        0,
                        true
                    );
                }

                window.setTimeout(() => {
                    applicationsSuppressClick =
                        false;
                }, 260);
            }

            applicationsViewport.addEventListener(
                'pointerup',
                event => {
                    finishApplicationsPointer(
                        event,
                        false
                    );
                }
            );

            applicationsViewport.addEventListener(
                'pointercancel',
                event => {
                    finishApplicationsPointer(
                        event,
                        true
                    );
                }
            );

            applicationsViewport.addEventListener(
                'click',
                event => {
                    if (!applicationsSuppressClick) {
                        return;
                    }

                    event.preventDefault();
                    event.stopPropagation();
                },
                true
            );
        }

        window.addEventListener(
            'resize',
            () => {
                const previousPageSize =
                    applicationsPageSize;

                const nextPageSize =
                    getApplicationsPageSize();

                if (
                    previousPageSize ===
                    nextPageSize
                ) {
                    setApplicationsTrackPosition(
                        0,
                        false
                    );
                    return;
                }

                applicationsPageSize =
                    nextPageSize;

                renderApplications(
                    displayedApplications,
                    {
                        preservePage: true
                    }
                );
            }
        );
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

    function filterApplicationsByCategory(applicationList) {
        if (!activeCategory) {
            return [...applicationList];
        }

        const normalizedCategory =
            normalizeText(activeCategory);

        return applicationList.filter(application =>
            normalizeText(application.category) ===
            normalizedCategory
        );
    }

    function filterApplicationsBySource(applicationList) {
        if (!activeSource) {
            return [...applicationList];
        }

        const normalizedSource =
            normalizeText(activeSource);

        return applicationList.filter(application =>
            normalizeText(application.source) ===
            normalizedSource
        );
    }

    function filterApplicationsByRating(applicationList) {
        if (!minimumRating) {
            return [...applicationList];
        }

        if (minimumRating === 'rated') {
            return applicationList.filter(application =>
                getApplicationRating(application) !== null
            );
        }

        const minimum =
            Number(minimumRating);

        if (!Number.isFinite(minimum)) {
            return [...applicationList];
        }

        return applicationList.filter(application => {
            const rating =
                getApplicationRating(application);

            return rating !== null &&
                rating >= minimum;
        });
    }

    function syncDirectoryFilterControls() {
        if (categoryFilter) {
            categoryFilter.value =
                activeCategory;
        }

        if (sourceFilter) {
            sourceFilter.value =
                activeSource;
        }

        if (ratingFilter) {
            ratingFilter.value =
                minimumRating;
        }
    }

    function updateDisplayedApplications() {
        const searchValue =
            searchInput ? searchInput.value : '';

        const searchFilteredApplications =
            filterApplications(searchValue);

        const categoryFilteredApplications =
            filterApplicationsByCategory(
                searchFilteredApplications
            );

        const sourceFilteredApplications =
            filterApplicationsBySource(
                categoryFilteredApplications
            );

        const ratingFilteredApplications =
            filterApplicationsByRating(
                sourceFilteredApplications
            );

        displayedApplications =
            sortApplications(
                ratingFilteredApplications
            );

        renderApplications(displayedApplications);

        updateSearchSuggestions(
            searchValue,
            displayedApplications
        );

        syncDirectoryFilterControls();
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
                ${createApplicationIcon(application.iconType, application.imageUrl, application.name)}

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
    }

    function resetDirectoryFilters() {
        activeCategory = '';
        activeSource = '';
        minimumRating = '';
        newestFirst = true;
        showAllApplicationsExpanded = false;

        if (searchInput) {
            searchInput.value = '';
        }

        updateClearSearchButton();
        hideSearchSuggestions();
        updateSortButtonState();
        updateDisplayedApplications();

        if (viewAllApplicationsButton) {
            viewAllApplicationsButton.classList.remove(
                'is-expanded'
            );

            const label =
                viewAllApplicationsButton.querySelector(
                    'span'
                );

            if (label) {
                label.textContent =
                    'View all applications';
            }
        }
    }

    categoryFilter?.addEventListener(
        'change',
        () => {
            activeCategory =
                String(
                    categoryFilter.value || ''
                ).trim();

            showAllApplicationsExpanded = false;
            updateDisplayedApplications();
        }
    );

    sourceFilter?.addEventListener(
        'change',
        () => {
            activeSource =
                String(
                    sourceFilter.value || ''
                ).trim();

            showAllApplicationsExpanded = false;
            updateDisplayedApplications();
        }
    );

    ratingFilter?.addEventListener(
        'change',
        () => {
            minimumRating =
                String(
                    ratingFilter.value || ''
                ).trim();

            showAllApplicationsExpanded = false;
            updateDisplayedApplications();
        }
    );

    resetFiltersButton?.addEventListener(
        'click',
        resetDirectoryFilters
    );

    function setApplicationViewMode(mode) {
        const nextMode =
            mode === 'list'
                ? 'list'
                : 'grid';

        applicationViewMode =
            nextMode;

        applicationsGrid?.classList.toggle(
            'is-list-view',
            nextMode === 'list'
        );

        applicationsGridViewButton?.classList.toggle(
            'is-active',
            nextMode === 'grid'
        );

        applicationsListViewButton?.classList.toggle(
            'is-active',
            nextMode === 'list'
        );

        applicationsGridViewButton?.setAttribute(
            'aria-pressed',
            String(
                nextMode === 'grid'
            )
        );

        applicationsListViewButton?.setAttribute(
            'aria-pressed',
            String(
                nextMode === 'list'
            )
        );

        showAllApplicationsExpanded = false;
        renderApplications(
            displayedApplications
        );
    }

    applicationsGridViewButton?.addEventListener(
        'click',
        () => {
            setApplicationViewMode(
                'grid'
            );
        }
    );

    applicationsListViewButton?.addEventListener(
        'click',
        () => {
            setApplicationViewMode(
                'list'
            );
        }
    );

    viewAllApplicationsButton?.addEventListener(
        'click',
        () => {
            showAllApplicationsExpanded =
                !showAllApplicationsExpanded;

            viewAllApplicationsButton.classList.toggle(
                'is-expanded',
                showAllApplicationsExpanded
            );

            const label =
                viewAllApplicationsButton.querySelector(
                    'span'
                );

            if (label) {
                label.textContent =
                    showAllApplicationsExpanded
                        ? 'Show fewer applications'
                        : 'View all applications';
            }

            renderApplications(
                displayedApplications
            );
        }
    );

    document.addEventListener(
        'keydown',
        event => {
            if (
                (event.ctrlKey || event.metaKey) &&
                event.key.toLowerCase() === 'k'
            ) {
                event.preventDefault();
                searchInput?.focus();
            }
        }
    );    /* =====================================================
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
            application.iconType,
            application.imageUrl,
            application.name
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

    const guideUrl =
        new URL('guide.html', window.location.href).href;

    async function openGuide() {
        try {
            const { data, error } =
                await supabaseClient.auth.getSession();

            if (error) {
                throw error;
            }

            if (data && data.session) {
                window.location.href = guideUrl;
                return;
            }
        } catch (error) {
            console.error(
                'OSGuide could not check the current login session.',
                error
            );
        }

        openModal(guideModal);
    }

    if (guideButton) {
        guideButton.addEventListener('click', () => {
            openGuide();
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
            button.addEventListener('click', async () => {
                const providerName =
                    button.textContent.trim();

                if (/google/i.test(providerName)) {
                    try {
                        const { error } =
                            await supabaseClient.auth.signInWithOAuth({
                                provider: 'google',
                                options: {
                                    redirectTo: guideUrl
                                }
                            });

                        if (error) {
                            throw error;
                        }
                    } catch (error) {
                        console.error(
                            'OSGuide Google sign-in failed.',
                            error
                        );

                        alert(
                            'Google sign-in could not be started. Please try again.'
                        );
                    }

                    return;
                }

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

        const favoriteApplicationButtons =
            document.querySelectorAll('[data-favorite-app]');

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

        favoriteApplicationButtons.forEach(button => {
            button.addEventListener('click', event => {
                event.preventDefault();
                event.stopPropagation();

                const applicationId =
                    button.dataset.favoriteApp;

                const favorite =
                    toggleApplicationFavorite(
                        applicationId
                    );

                button.classList.toggle(
                    'is-favorite',
                    favorite
                );

                button.setAttribute(
                    'aria-pressed',
                    String(favorite)
                );

                const application =
                    getApplicationById(
                        applicationId
                    );

                const applicationName =
                    application?.name ||
                    'Application';

                button.setAttribute(
                    'aria-label',
                    `${favorite ? 'Remove' : 'Add'} ${applicationName} ${favorite ? 'from' : 'to'} favorites`
                );

                button.setAttribute(
                    'title',
                    favorite
                        ? 'Remove from favorites'
                        : 'Add to favorites'
                );

                showNotification(
                    favorite
                        ? `${applicationName} added to favorites.`
                        : `${applicationName} removed from favorites.`
                );
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
                    const action =
                        link.dataset.footerAction ||
                        '';

                    const href =
                        link.getAttribute('href');

                    if (
                        href &&
                        href !== '#'
                    ) {
                        return;
                    }

                    event.preventDefault();

                    if (action === 'guide') {
                        openGuide();
                        return;
                    }

                    if (action === 'fdroid') {
                        openModal(fdroidModal);
                        return;
                    }

                    const linkName =
                        link.textContent.trim();

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

    renderApplications = function (
        applicationList,
        options = {}
    ) {
        renderApplicationsWithGridState(
            applicationList,
            options
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

    const supabaseApplications = Array.isArray(data)
        ? data.map((app) => ({
            id: String(app.id),
            slug: app.slug || '',
            name: app.name || '',
            description: app.description || '',
            longDescription: app.long_description || app.description || '',
            version: app.version || '',
            size: app.size || 'Unknown size',
            source: app.source || 'F-Droid',
            license: app.license || '',
            platform: app.platform || 'Android',
            category: app.category || '',
            added: app.added || '',
            downloadUrl: app.download_url || '',
            iconType: app.icon_type || 'default',
            imageUrl: app.image_url || '',
            rating:
                app.rating ??
                app.average_rating ??
                null,
            ratingCount:
                app.rating_count ??
                app.ratings_count ??
                app.reviews_count ??
                0
        }))
        : [];

    applications.splice(
        0,
        applications.length,
        ...supabaseApplications
    );
} catch (error) {
    applications.splice(0, applications.length);

    console.error(
        'Could not load applications from Supabase.',
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
       48. Side Navigation and Featured Application
    ===================================================== */

    let sideNavigationLastFocus = null;
    let featuredApplicationId = '9';

    function openSideNavigation() {
        if (!sideNavigationShell || !sideNavigation) {
            return;
        }

        sideNavigationLastFocus = document.activeElement;
        sideNavigationShell.hidden = false;
        sideNavigation.setAttribute('aria-hidden', 'false');
        body.classList.add('side-navigation-open');

        if (menuButton) {
            menuButton.setAttribute('aria-expanded', 'true');
        }

        requestAnimationFrame(() => {
            sideNavigationShell.classList.add('is-open');
        });

        if (sideNavigationClose) {
            sideNavigationClose.focus();
        }
    }

    function closeSideNavigation() {
        if (!sideNavigationShell || !sideNavigation) {
            return;
        }

        sideNavigationShell.classList.remove('is-open');
        sideNavigation.setAttribute('aria-hidden', 'true');
        body.classList.remove('side-navigation-open');

        if (menuButton) {
            menuButton.setAttribute('aria-expanded', 'false');
        }

        window.setTimeout(() => {
            if (!sideNavigationShell.classList.contains('is-open')) {
                sideNavigationShell.hidden = true;
            }
        }, 240);

        if (
            sideNavigationLastFocus &&
            typeof sideNavigationLastFocus.focus === 'function'
        ) {
            sideNavigationLastFocus.focus();
        }

        sideNavigationLastFocus = null;
    }

    function scrollToSection(selector) {
        const section = document.querySelector(selector);

        if (!section) {
            return;
        }

        section.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }

    function setActiveSideNavigationItem(activeButton) {
        document
            .querySelectorAll(
                '.side-navigation-item, .category-card'
            )
            .forEach(button => {
                button.classList.remove('is-active');
                button.setAttribute('aria-pressed', 'false');
            });

        if (activeButton) {
            activeButton.classList.add('is-active');
            activeButton.setAttribute('aria-pressed', 'true');
        }
    }

    function clearApplicationSearchForBrowse() {
        if (!searchInput) {
            return;
        }

        searchInput.value = '';
        updateClearSearchButton();
        hideSearchSuggestions();
    }

    function showAllApplications(activeButton = null) {
        activeCategory = '';
        activeSource = '';
        minimumRating = '';
        browseMode = 'home';
        newestFirst = true;
        showAllApplicationsExpanded = false;

        clearApplicationSearchForBrowse();
        updateSortButtonState();
        updateDisplayedApplications();
        setActiveSideNavigationItem(activeButton);
    }

    function showCategoryApplications(category, activeButton = null) {
        activeCategory =
            String(category || '').trim();

        browseMode = 'category';
        newestFirst = true;
        showAllApplicationsExpanded = false;

        clearApplicationSearchForBrowse();
        updateSortButtonState();
        updateDisplayedApplications();
        setActiveSideNavigationItem(activeButton);
        scrollToSection('.applications-section');
    }

    function showNewestApplications(activeButton = null) {
        activeCategory = '';
        browseMode = 'new';
        newestFirst = true;
        showAllApplicationsExpanded = false;

        clearApplicationSearchForBrowse();
        updateSortButtonState();
        updateDisplayedApplications();
        setActiveSideNavigationItem(activeButton);
        scrollToSection('.applications-section');
    }

    function handleSideNavigationAction(action, activeButton = null) {
        closeSideNavigation();

        window.setTimeout(() => {
            switch (action) {
                case 'home':
                    showAllApplications(activeButton);
                    window.scrollTo({
                        top: 0,
                        behavior: 'smooth'
                    });
                    break;

                case 'featured':
                    setActiveSideNavigationItem(activeButton);
                    scrollToSection('#featured-section');
                    break;

                case 'new':
                    showNewestApplications(activeButton);
                    break;

                case 'guide':
                    openGuide();
                    break;

                case 'fdroid':
                    openModal(fdroidModal);
                    break;

                default:
                    break;
            }
        }, 120);
    }

    function attachSideNavigationEvents() {
        if (menuButton) {
            menuButton.addEventListener('click', openSideNavigation);
        }

        if (sideNavigationClose) {
            sideNavigationClose.addEventListener('click', closeSideNavigation);
        }

        if (sideNavigationBackdrop) {
            sideNavigationBackdrop.addEventListener('click', closeSideNavigation);
        }

        if (accountCard) {
            accountCard.addEventListener('click', () => {
                closeSideNavigation();
                window.setTimeout(() => openGuide(), 120);
            });
        }

        document.querySelectorAll('[data-side-action]').forEach(button => {
            button.addEventListener('click', () => {
                handleSideNavigationAction(
                    button.dataset.sideAction,
                    button
                );
            });
        });

        document.querySelectorAll('[data-side-category]').forEach(button => {
            button.addEventListener('click', () => {
                closeSideNavigation();

                window.setTimeout(() => {
                    showCategoryApplications(
                        button.dataset.sideCategory,
                        button
                    );
                }, 120);
            });
        });

        document.querySelectorAll('.category-card[data-category]').forEach(button => {
            button.addEventListener('click', () => {
                showCategoryApplications(
                    button.dataset.category,
                    button
                );
            });
        });

        document.addEventListener('keydown', event => {
            if (
                event.key === 'Escape' &&
                sideNavigationShell &&
                !sideNavigationShell.hidden
            ) {
                event.preventDefault();
                closeSideNavigation();
            }
        });
    }

    function chooseFeaturedApplication() {
        if (applications.length === 0) {
            return null;
        }

        const termux = applications.find(application =>
            normalizeText(application.name) === 'termux' ||
            normalizeText(application.slug) === 'termux'
        );

        if (termux) {
            return termux;
        }

        return [...applications].sort((first, second) => {
            return new Date(second.added).getTime() - new Date(first.added).getTime();
        })[0];
    }

    function renderFeaturedApplication() {
        const application = chooseFeaturedApplication();

        if (
            !application ||
            !featuredSection ||
            !featuredApplicationCard ||
            !featuredApplicationVisual ||
            !featuredApplicationName ||
            !featuredApplicationDescription ||
            !featuredApplicationMeta
        ) {
            console.warn('Featured application data could not be loaded; keeping the built-in fallback card visible.');
            return;
        }

        featuredApplicationId = application.id;
        featuredApplicationVisual.innerHTML = createApplicationIcon(
            application.iconType,
            application.imageUrl,
            application.name
        );
        featuredApplicationName.textContent = application.name;
        featuredApplicationDescription.textContent = application.description;
        featuredApplicationMeta.innerHTML = `
            <span>${escapeHTML(application.version)}</span>
            <span>${escapeHTML(application.size)}</span>
            <span>${escapeHTML(application.category)}</span>
            <span>Source: ${escapeHTML(application.source)}</span>
        `;
        featuredApplicationCard.setAttribute(
            'aria-label',
            `View ${application.name} information`
        );
        featuredSection.hidden = false;
    }

    function attachFeaturedApplicationEvent() {
        if (!featuredApplicationCard) {
            return;
        }

        featuredApplicationCard.addEventListener('click', () => {
            if (featuredApplicationId) {
                openApplicationModal(featuredApplicationId);
            }
        });
    }


    function renderCategoryCounts() {
        document
            .querySelectorAll(
                '[data-category-count]'
            )
            .forEach(element => {
                const category =
                    String(
                        element.dataset.categoryCount ||
                        ''
                    ).trim();

                const count =
                    applications.filter(
                        application =>
                            normalizeText(
                                application.category
                            ) ===
                            normalizeText(
                                category
                            )
                    ).length;

                element.textContent =
                    `${count} ${count === 1 ? 'app' : 'apps'}`;
            });
    }

    /* =====================================================
       47B. Why OSGuide Detail Windows
       The four existing cards keep their visible design. This block only
       controls the information window that appears after interaction.
    ===================================================== */

    const whyOSGuideTopics = {
        trusted: {
            title: 'Trusted sources',
            description:
                'OSGuide lists applications from trusted open-source sources. We believe transparency is the foundation of trust.',
            secondaryLabel: 'Learn about F-Droid',
            secondaryAction: 'fdroid',
            content: `
                <div class="why-info-column">
                    <section class="why-info-section">
                        <h3>Where does the information come from?</h3>

                        <div class="why-info-list">
                            <div class="why-info-list-item">
                                <span class="why-info-mini-icon">
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <path d="M6 7.5H18V19H6V7.5Z"></path>
                                        <path d="M8 7.5L9.5 4.5M16 7.5L14.5 4.5"></path>
                                        <circle cx="9.5" cy="12" r="1"></circle>
                                        <circle cx="14.5" cy="12" r="1"></circle>
                                    </svg>
                                </span>
                                <div>
                                    <strong>F-Droid</strong>
                                    <p>A trusted open-source app repository with transparent project information.</p>
                                </div>
                            </div>

                            <div class="why-info-list-item">
                                <span class="why-info-mini-icon">
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <path d="M12 3.5A8.5 8.5 0 0 0 9.3 20.1"></path>
                                        <path d="M12 3.5A8.5 8.5 0 0 1 14.7 20.1"></path>
                                        <path d="M5 8.5H19M4 14.5H20"></path>
                                    </svg>
                                </span>
                                <div>
                                    <strong>GitHub</strong>
                                    <p>Official project repositories maintained by developers and open-source teams.</p>
                                </div>
                            </div>

                            <div class="why-info-list-item">
                                <span class="why-info-mini-icon">
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <circle cx="12" cy="12" r="8.5"></circle>
                                        <path d="M8.5 12L11 14.5L16 9.5"></path>
                                    </svg>
                                </span>
                                <div>
                                    <strong>Other official sources</strong>
                                    <p>When available, OSGuide may use an official website or another reputable project source.</p>
                                </div>
                            </div>
                        </div>
                    </section>
                </div>

                <div class="why-info-column">
                    <section class="why-info-section">
                        <h3>What we verify</h3>

                        <ul class="why-info-check-list">
                            <li>Application identity and Package ID</li>
                            <li>Source link points to the intended project</li>
                            <li>License information when it is available</li>
                            <li>We do not modify application files</li>
                        </ul>
                    </section>

                    <aside class="why-info-warning" role="note">
                        <span class="why-info-warning-icon">
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M12 3L21 20H3L12 3Z"></path>
                                <path d="M12 9V14"></path>
                                <circle cx="12" cy="17" r="0.8"></circle>
                            </svg>
                        </span>
                        <div>
                            <strong>What this does not mean</strong>
                            <p>We do not review every line of code or guarantee that every APK is safe. Always review the source and decide what you trust before installing an application.</p>
                        </div>
                    </aside>
                </div>
            `
        },

        downloads: {
            title: 'Simple downloads',
            description:
                'We make the download process clear and straightforward. No confusing redirects. No deceptive buttons.',
            secondaryLabel: 'Learn more about sources',
            secondaryAction: 'trusted',
            content: `
                <div class="why-info-column">
                    <section class="why-info-section">
                        <h3>How downloading works</h3>

                        <div class="why-info-steps">
                            <div class="why-info-step">
                                <span>1</span>
                                <div>
                                    <strong>Choose an application</strong>
                                    <p>Browse or search OSGuide until you find the app you want.</p>
                                </div>
                            </div>

                            <div class="why-info-step">
                                <span>2</span>
                                <div>
                                    <strong>Review details &amp; source</strong>
                                    <p>Check version, size, license and the source before downloading.</p>
                                </div>
                            </div>

                            <div class="why-info-step">
                                <span>3</span>
                                <div>
                                    <strong>Download the file</strong>
                                    <p>OSGuide takes you to the resolved APK link or the verified source route.</p>
                                </div>
                            </div>
                        </div>
                    </section>
                </div>

                <div class="why-info-column">
                    <section class="why-info-section">
                        <h3>What OSGuide does</h3>

                        <ul class="why-info-check-list">
                            <li>Provides download links resolved from the original or known project source</li>
                            <li>Shows version, size and source clearly</li>
                            <li>Avoids deceptive download buttons and unnecessary redirects</li>
                            <li>Reduces confusion while keeping the source visible</li>
                        </ul>
                    </section>

                    <aside class="why-info-warning" role="note">
                        <span class="why-info-warning-icon">
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M12 3L21 20H3L12 3Z"></path>
                                <path d="M12 9V14"></path>
                                <circle cx="12" cy="17" r="0.8"></circle>
                            </svg>
                        </span>
                        <div>
                            <strong>What you should check</strong>
                            <ul>
                                <li>Verify the source shown</li>
                                <li>Check the application name and Package ID</li>
                                <li>Install apps only from sources you trust</li>
                            </ul>
                        </div>
                    </aside>
                </div>
            `
        },

        guides: {
            title: 'Practical guides',
            description:
                'OSGuide Guides help you understand applications before you decide to download them.',
            secondaryLabel: 'Explore Guides',
            secondaryAction: 'guide',
            content: `
                <div class="why-info-column">
                    <div class="why-info-list why-info-guide-list">
                        <div class="why-info-list-item">
                            <span class="why-info-mini-icon">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <circle cx="11" cy="11" r="6"></circle>
                                    <path d="M15.5 15.5L20 20"></path>
                                </svg>
                            </span>
                            <div>
                                <strong>Understand the app</strong>
                                <p>Learn what the application does and its main features.</p>
                            </div>
                        </div>

                        <div class="why-info-list-item">
                            <span class="why-info-mini-icon">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 3L19 6.5V11.5C19 16 16 19.3 12 21C8 19.3 5 16 5 11.5V6.5L12 3Z"></path>
                                    <path d="M9 12L11 14L15 10"></path>
                                </svg>
                            </span>
                            <div>
                                <strong>Discover use cases</strong>
                                <p>See real-world scenarios and understand how the app can help you.</p>
                            </div>
                        </div>

                        <div class="why-info-list-item">
                            <span class="why-info-mini-icon">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M5 5H19V19H5V5Z"></path>
                                    <path d="M9 9H15M9 13H15M9 17H13"></path>
                                </svg>
                            </span>
                            <div>
                                <strong>Learn step by step</strong>
                                <p>Follow clear explanations and simple guides at your own pace.</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="why-info-column">
                    <section class="why-info-feature-box">
                        <div class="why-info-feature-heading">
                            <span class="why-info-mini-icon">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M5 4.5H15.5L19 8V19.5H5V4.5Z"></path>
                                    <path d="M15.5 4.5V8H19"></path>
                                </svg>
                            </span>
                            <div>
                                <strong>Available in the Guide section</strong>
                                <p>Access detailed guides, tips and best practices in the Guide section.</p>
                            </div>
                        </div>

                        <ul class="why-info-check-list why-info-compact-checks">
                            <li>No download required to learn</li>
                            <li>Helpful for beginners and advanced users</li>
                            <li>Guides grow with the catalog</li>
                        </ul>
                    </section>
                </div>
            `
        },

        updates: {
            title: 'Continuously updated',
            description:
                'OSGuide is a living catalog. We keep improving, adding and updating information over time.',
            secondaryLabel: '',
            secondaryAction: '',
            content: `
                <div class="why-info-column">
                    <div class="why-info-list">
                        <div class="why-info-list-item">
                            <span class="why-info-mini-icon">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 3L20 7V12C20 17 16.5 20.5 12 22C7.5 20.5 4 17 4 12V7L12 3Z"></path>
                                </svg>
                            </span>
                            <div>
                                <strong>New applications</strong>
                                <p>We add new open-source applications as they are reviewed for the catalog.</p>
                            </div>
                        </div>

                        <div class="why-info-list-item">
                            <span class="why-info-mini-icon">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M20 7V12H15"></path>
                                    <path d="M18.5 8.5A7.5 7.5 0 1 0 19 15"></path>
                                </svg>
                            </span>
                            <div>
                                <strong>Updated information</strong>
                                <p>App details such as version, size, source and description can be refreshed when changes occur.</p>
                            </div>
                        </div>

                        <div class="why-info-list-item">
                            <span class="why-info-mini-icon">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M4 5.5C7 4.8 9.7 5.2 12 6.5V20C9.7 18.7 7 18.3 4 19V5.5Z"></path>
                                    <path d="M20 5.5C17 4.8 14.3 5.2 12 6.5V20C14.3 18.7 17 18.3 20 19V5.5Z"></path>
                                </svg>
                            </span>
                            <div>
                                <strong>Guides grow with the catalog</strong>
                                <p>More applications can bring more practical guides and helpful content over time.</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="why-info-column">
                    <section class="why-info-feature-box">
                        <div class="why-info-feature-heading">
                            <span class="why-info-mini-icon">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <circle cx="12" cy="12" r="8.5"></circle>
                                    <path d="M12 7V12L15 14"></path>
                                </svg>
                            </span>
                            <div>
                                <strong>How it works</strong>
                                <p>Our admin system helps update and publish application metadata. This keeps the catalog organized while changes are reviewed.</p>
                            </div>
                        </div>
                    </section>

                    <aside class="why-info-note" role="note">
                        <span class="why-info-note-icon">
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                                <circle cx="12" cy="12" r="8.5"></circle>
                                <path d="M12 10.5V16"></path>
                                <circle cx="12" cy="7.5" r="0.8"></circle>
                            </svg>
                        </span>
                        <div>
                            <strong>Note</strong>
                            <p>We aim to keep information up to date, but there may be some delay after changes at the original source.</p>
                        </div>
                    </aside>
                </div>
            `
        }
    };

    function populateWhyOSGuideModal(topicKey, triggerCard = null) {
        const topic =
            whyOSGuideTopics[topicKey];

        if (
            !topic ||
            !whyInfoModal ||
            !whyInfoModalTitle ||
            !whyInfoModalDescription ||
            !whyInfoModalContent
        ) {
            return false;
        }

        whyInfoModal.dataset.whyTopic = topicKey;
        whyInfoModalTitle.textContent = topic.title;
        whyInfoModalDescription.textContent = topic.description;
        whyInfoModalContent.innerHTML = topic.content;

        if (whyInfoModalIcon) {
            const sourceIcon =
                triggerCard?.querySelector('.why-icon svg');

            whyInfoModalIcon.innerHTML =
                sourceIcon
                    ? sourceIcon.outerHTML
                    : '';
        }

        if (
            whyInfoSecondaryButton &&
            whyInfoSecondaryLabel
        ) {
            const hasSecondaryAction =
                Boolean(
                    topic.secondaryLabel &&
                    topic.secondaryAction
                );

            whyInfoSecondaryButton.hidden =
                !hasSecondaryAction;

            whyInfoSecondaryButton.dataset.whyAction =
                topic.secondaryAction || '';

            whyInfoSecondaryLabel.textContent =
                topic.secondaryLabel || '';
        }

        return true;
    }

    function openWhyOSGuideTopic(topicKey, triggerCard = null) {
        if (
            populateWhyOSGuideModal(
                topicKey,
                triggerCard
            )
        ) {
            openModal(whyInfoModal);
        }
    }

    function attachWhyOSGuideEvents() {
        document
            .querySelectorAll('[data-why-topic]')
            .forEach(card => {
                const openCard = () => {
                    openWhyOSGuideTopic(
                        card.dataset.whyTopic,
                        card
                    );
                };

                card.addEventListener(
                    'click',
                    openCard
                );

                card.addEventListener(
                    'keydown',
                    event => {
                        if (
                            event.key !== 'Enter' &&
                            event.key !== ' '
                        ) {
                            return;
                        }

                        event.preventDefault();
                        openCard();
                    }
                );
            });

        if (whyInfoSecondaryButton) {
            whyInfoSecondaryButton.addEventListener(
                'click',
                () => {
                    const action =
                        whyInfoSecondaryButton.dataset.whyAction || '';

                    if (action === 'fdroid') {
                        closeModal(whyInfoModal);
                        openModal(fdroidModal);
                        return;
                    }

                    if (action === 'guide') {
                        closeModal(whyInfoModal);
                        openModal(guideModal);
                        return;
                    }

                    if (action === 'trusted') {
                        const trustedCard =
                            document.querySelector(
                                '[data-why-topic="trusted"]'
                            );

                        populateWhyOSGuideModal(
                            'trusted',
                            trustedCard
                        );
                    }
                }
            );
        }
    }

    function attachSupportEvents() {
        document
            .querySelectorAll(
                '[data-support-method]'
            )
            .forEach(button => {
                button.addEventListener(
                    'click',
                    event => {
                        const method =
                            button.dataset.supportMethod ||
                            'Support';

                        if (method === 'Wallet') {
                            event.preventDefault();
                            openModal(walletSupportModal);
                            return;
                        }

                        if (
                            button.tagName === 'A' &&
                            button.getAttribute('href') &&
                            button.getAttribute('href') !== '#'
                        ) {
                            return;
                        }

                        event.preventDefault();

                        showNotification(
                            `${method} support is not available yet.`
                        );
                    }
                );
            });

        if (walletCopyButton) {
            walletCopyButton.addEventListener(
                'click',
                async () => {
                    const walletAddress =
                        walletCopyButton.dataset.walletAddress ||
                        '0xe74c140d827d2e4f5a1a0eba58176ab507cbdeab';

                    try {
                        await navigator.clipboard.writeText(
                            walletAddress
                        );

                        walletCopyButton.classList.add(
                            'is-copied'
                        );

                        const label =
                            walletCopyButton.querySelector(
                                'span'
                            );

                        if (label) {
                            label.textContent =
                                'Copied';
                        }

                        showNotification(
                            'USDT ERC20 wallet address copied.'
                        );

                        window.setTimeout(() => {
                            walletCopyButton.classList.remove(
                                'is-copied'
                            );

                            if (label) {
                                label.textContent =
                                    'Copy address';
                            }
                        }, 1800);
                    } catch (error) {
                        console.warn(
                            'OSGuide could not copy the wallet address.',
                            error
                        );

                        showNotification(
                            'Copy failed. Press and hold the wallet address to copy it manually.'
                        );
                    }
                }
            );
        }
    }

    /* =====================================================
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
            loadFavoriteApplications();
            renderCategoryCounts();
            attachBrandHomeEvent();
            attachGuideLoginEvents();
            attachFooterLinkEvents();
            attachWhyOSGuideEvents();
            attachSupportEvents();
            attachSideNavigationEvents();
            attachFeaturedApplicationEvent();
            attachApplicationsPagingEvents();

            setActiveSideNavigationItem(
                document.querySelector(
                    '[data-side-action="home"]'
                )
            );

            displayedApplications =
                filterApplicationsByRating(
                    filterApplicationsBySource(
                        filterApplicationsByCategory(
                            sortApplications(
                                filterApplications(
                                    searchInput
                                        ? searchInput.value
                                        : ''
                                )
                            )
                        )
                    )
                );

            syncDirectoryFilterControls();

            renderApplications(
                displayedApplications
            );
            renderFeaturedApplication();

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
