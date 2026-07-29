'use strict';

document.addEventListener('DOMContentLoaded', async () => {
    const SUPABASE_URL =
        'https://rqvicenfdzlleureteis.supabase.co';

    const SUPABASE_PUBLISHABLE_KEY =
        'sb_publishable_U64um_oKyNG0zXHQu6PuTg_lR9rSIwA';

    const SUPABASE_REST_URL =
        `${SUPABASE_URL}/rest/v1`;

    async function fetchFromSupabase(path) {
        const response = await fetch(
            `${SUPABASE_REST_URL}${path}`,
            {
                method: 'GET',
                headers: {
                    apikey: SUPABASE_PUBLISHABLE_KEY,
                    Authorization:
                        `Bearer ${SUPABASE_PUBLISHABLE_KEY}`,
                    Accept: 'application/json'
                }
            }
        );

        if (!response.ok) {
            const message = await response.text();

            throw new Error(
                `Supabase request failed (${response.status}): ${message}`
            );
        }

        return response.json();
    }

    const backButton =
        document.getElementById('guide-back-button');

    const guideMain =
        document.getElementById('guide-main');

    const appIcon =
        document.getElementById('guide-app-icon');

    const appCategory =
        document.getElementById('guide-app-category');

    const appName =
        document.getElementById('guide-app-name');

    const appVersion =
        document.getElementById('guide-app-version');

    const downloadButton =
        document.getElementById('guide-download-button');

    const aboutContent =
        document.getElementById('guide-about-content');

    const installationContent =
        document.getElementById('guide-installation-content');

    const firstStepsContent =
        document.getElementById('guide-first-steps-content');

    const tutorialsContent =
        document.getElementById('guide-tutorials-content');

    const tipsContent =
        document.getElementById('guide-tips-content');

    const faqContent =
        document.getElementById('guide-faq-content');

    const relatedAppsContainer =
        document.getElementById('guide-related-apps');

    const progressValue =
        document.getElementById('guide-progress-value');

    const progressBar =
        document.getElementById('guide-progress-bar');

    const progressTrack =
        document.querySelector('.guide-progress-track');

    const params =
        new URLSearchParams(window.location.search);

    const appId =
        String(params.get('id') || '').trim();

    const completedSections =
        new Set();

    function escapeHTML(value) {
        return String(value || '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    function applySavedTheme() {
        let savedTheme = 'light';

        try {
            savedTheme =
                localStorage.getItem('osguide-theme') || 'light';
        } catch (error) {
            console.warn(
                'OSGuide could not read the saved theme.',
                error
            );
        }

        const useDarkTheme =
            savedTheme === 'dark';

        document.body.classList.toggle(
            'dark-theme',
            useDarkTheme
        );

        document.body.classList.toggle(
            'light-theme',
            !useDarkTheme
        );
    }

    function showError(message) {
        if (!guideMain) {
            return;
        }

        guideMain.innerHTML = `
            <section class="guide-error-state">
                <h1>Guide unavailable</h1>
                <p>${escapeHTML(message)}</p>
                <a
                    class="guide-download-button"
                    href="index.html"
                    style="margin-top:18px"
                >
                    Return to OSGuide
                </a>
            </section>
        `;
    }

    function setLoadingState() {
        if (!guideMain) {
            return;
        }

        guideMain.setAttribute(
            'aria-busy',
            'true'
        );
    }

    function clearLoadingState() {
        if (!guideMain) {
            return;
        }

        guideMain.removeAttribute(
            'aria-busy'
        );
    }

    function normalizeApplication(row) {
        return {
            id: String(row.id || ''),
            name: row.name || 'Application',
            description: row.description || '',
            longDescription:
                row.long_description ||
                row.description ||
                '',
            version: row.version || 'Unknown version',
            size: row.size || '',
            source: row.source || 'F-Droid',
            license: row.license || '',
            platform: row.platform || 'Android',
            category: row.category || 'Application',
            downloadUrl: row.download_url || '#',
            imageUrl: row.image_url || ''
        };
    }

    function createFallbackIcon(applicationName) {
        const firstLetter =
            String(applicationName || 'A')
                .trim()
                .charAt(0)
                .toUpperCase();

        const svg = `
            <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 96 96"
            >
                <rect
                    width="96"
                    height="96"
                    rx="22"
                    fill="#2563eb"
                />
                <text
                    x="48"
                    y="60"
                    text-anchor="middle"
                    font-family="Arial, sans-serif"
                    font-size="44"
                    font-weight="700"
                    fill="white"
                >${escapeHTML(firstLetter)}</text>
            </svg>
        `;

        return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
    }

    function updateApplicationHeader(application) {
        document.title =
            `${application.name} Guide | OSGuide`;

        document.body.dataset.appId =
            application.id;

        if (appName) {
            appName.textContent =
                application.name;
        }

        if (appCategory) {
            appCategory.textContent =
                `${application.category} Guide`;
        }

        if (appVersion) {
            const versionText =
                application.size
                    ? `Version ${application.version} · ${application.size}`
                    : `Version ${application.version}`;

            appVersion.textContent =
                versionText;
        }

        if (appIcon) {
            appIcon.src =
                application.imageUrl ||
                createFallbackIcon(application.name);

            appIcon.alt =
                `${application.name} logo`;

            appIcon.onerror = () => {
                appIcon.onerror = null;
                appIcon.src =
                    createFallbackIcon(application.name);
            };
        }

        if (downloadButton) {
            downloadButton.href =
                application.downloadUrl || '#';

            downloadButton.setAttribute(
                'aria-label',
                `Download ${application.name}`
            );
        }
    }

    function updateGuideContent(application) {
        if (aboutContent) {
            aboutContent.innerHTML = `
                <p>${escapeHTML(application.longDescription)}</p>

                <div class="guide-note">
                    <strong>Source:</strong>
                    ${escapeHTML(application.source)}
                    ·
                    <strong>License:</strong>
                    ${escapeHTML(application.license || 'Not specified')}
                    ·
                    <strong>Platform:</strong>
                    ${escapeHTML(application.platform)}
                </div>
            `;
        }

        if (installationContent) {
            installationContent.innerHTML = `
                <ol>
                    <li>
                        Press <strong>Download APK</strong> above.
                    </li>
                    <li>
                        Open the downloaded APK file on your Android device.
                    </li>
                    <li>
                        Allow installation from the browser or file manager
                        only when Android asks you.
                    </li>
                    <li>
                        Review the permissions and finish installation.
                    </li>
                </ol>

                <div class="guide-warning">
                    Download applications only from the official source
                    shown by OSGuide.
                </div>
            `;
        }

        if (firstStepsContent) {
            firstStepsContent.innerHTML = `
                <ol>
                    <li>
                        Open ${escapeHTML(application.name)}.
                    </li>
                    <li>
                        Read the first-run information carefully.
                    </li>
                    <li>
                        Grant only the permissions required for the
                        feature you intend to use.
                    </li>
                    <li>
                        Explore the main settings before starting.
                    </li>
                </ol>

                <div class="guide-success">
                    The detailed first-use walkthrough for this application
                    will be added from the OSGuide admin system.
                </div>
            `;
        }

        if (tutorialsContent) {
            tutorialsContent.innerHTML = `
                <button class="guide-tutorial-card" type="button">
                    <span>
                        <strong>Getting Started</strong>
                        <small>Learn the essential controls</small>
                    </span>
                </button>

                <button class="guide-tutorial-card" type="button">
                    <span>
                        <strong>Privacy &amp; Permissions</strong>
                        <small>Use the application safely</small>
                    </span>
                </button>

                <button class="guide-tutorial-card" type="button">
                    <span>
                        <strong>Useful Features</strong>
                        <small>Discover practical tools</small>
                    </span>
                </button>
            `;
        }

        if (tipsContent) {
            tipsContent.innerHTML = `
                <ul>
                    <li>
                        Keep ${escapeHTML(application.name)} updated.
                    </li>
                    <li>
                        Review permissions after major updates.
                    </li>
                    <li>
                        Export or back up important settings when supported.
                    </li>
                    <li>
                        Avoid unofficial modified APK files.
                    </li>
                </ul>
            `;
        }

        if (faqContent) {
            faqContent.innerHTML = `
                <h3>Is this application open source?</h3>
                <p>
                    OSGuide lists applications from F-Droid and displays
                    the declared license when available.
                </p>

                <h3>Why does Android block installation?</h3>
                <p>
                    Android may ask you to allow installation from the
                    browser or file manager used to open the APK.
                </p>

                <h3>Where will the complete guide appear?</h3>
                <p>
                    Detailed app-specific lessons will be managed from
                    the OSGuide administration system.
                </p>
            `;
        }
    }

    function renderRelatedApps(applications, currentApplication) {
        if (!relatedAppsContainer) {
            return;
        }

        const relatedApps =
            applications
                .filter(application => {
                    return (
                        application.id !== currentApplication.id &&
                        application.category === currentApplication.category
                    );
                })
                .slice(0, 4);

        const fallbackApps =
            applications
                .filter(application => {
                    return application.id !== currentApplication.id;
                })
                .slice(0, 4);

        const finalApps =
            relatedApps.length > 0
                ? relatedApps
                : fallbackApps;

        if (finalApps.length === 0) {
            relatedAppsContainer.innerHTML = `
                <p>No related applications are available yet.</p>
            `;
            return;
        }

        relatedAppsContainer.innerHTML =
            finalApps
                .map(application => {
                    const iconUrl =
                        application.imageUrl ||
                        createFallbackIcon(application.name);

                    return `
                        <a
                            class="guide-related-app"
                            href="guide.html?id=${encodeURIComponent(application.id)}"
                        >
                            <img
                                src="${escapeHTML(iconUrl)}"
                                alt="${escapeHTML(application.name)} logo"
                                loading="lazy"
                                referrerpolicy="no-referrer"
                            >

                            <span>
                                <strong>${escapeHTML(application.name)}</strong>
                                <small>${escapeHTML(application.category)}</small>
                            </span>
                        </a>
                    `;
                })
                .join('');
    }

    function updateProgress() {
        const buttons =
            Array.from(
                document.querySelectorAll(
                    '.guide-accordion-button'
                )
            );

        const totalSections =
            buttons.length;

        const percentage =
            totalSections === 0
                ? 0
                : Math.round(
                    completedSections.size /
                    totalSections *
                    100
                );

        if (progressValue) {
            progressValue.textContent =
                `${percentage}%`;
        }

        if (progressBar) {
            progressBar.style.width =
                `${percentage}%`;
        }

        if (progressTrack) {
            progressTrack.setAttribute(
                'aria-valuenow',
                String(percentage)
            );
        }

        try {
            localStorage.setItem(
                `osguide-guide-progress-${appId}`,
                JSON.stringify(
                    Array.from(completedSections)
                )
            );
        } catch (error) {
            console.warn(
                'OSGuide could not save guide progress.',
                error
            );
        }
    }

    function restoreProgress() {
        try {
            const savedProgress =
                JSON.parse(
                    localStorage.getItem(
                        `osguide-guide-progress-${appId}`
                    ) || '[]'
                );

            if (Array.isArray(savedProgress)) {
                savedProgress.forEach(index => {
                    completedSections.add(
                        Number(index)
                    );
                });
            }
        } catch (error) {
            console.warn(
                'OSGuide could not restore guide progress.',
                error
            );
        }

        updateProgress();
    }

    function attachAccordionEvents() {
        const accordionButtons =
            document.querySelectorAll(
                '.guide-accordion-button'
            );

        accordionButtons.forEach((button, index) => {
            button.addEventListener('click', () => {
                const expanded =
                    button.getAttribute(
                        'aria-expanded'
                    ) === 'true';

                const content =
                    button.nextElementSibling;

                button.setAttribute(
                    'aria-expanded',
                    String(!expanded)
                );

                if (content) {
                    content.hidden =
                        expanded;
                }

                if (!expanded) {
                    completedSections.add(index);
                    updateProgress();
                }
            });
        });
    }

    async function loadGuide() {
        if (!appId) {
            window.location.replace(
                'index.html'
            );
            return;
        }

        setLoadingState();

        const applicationRows =
            await fetchFromSupabase(
                `/applications` +
                `?select=*` +
                `&id=eq.${encodeURIComponent(appId)}` +
                `&is_published=eq.true` +
                `&limit=1`
            );

        const applicationRow =
            Array.isArray(applicationRows)
                ? applicationRows[0]
                : null;

        if (!applicationRow) {
            showError(
                'This application does not exist or is not published.'
            );
            return;
        }

        let relatedRows = [];

        try {
            relatedRows =
                await fetchFromSupabase(
                    '/applications' +
                    '?select=*' +
                    '&is_published=eq.true' +
                    '&order=added.desc'
                );
        } catch (relatedError) {
            console.warn(
                'Related applications could not be loaded.',
                relatedError
            );
        }

        const application =
            normalizeApplication(applicationRow);

        const applications =
            Array.isArray(relatedRows)
                ? relatedRows.map(normalizeApplication)
                : [];

        updateApplicationHeader(application);
        updateGuideContent(application);
        renderRelatedApps(
            applications,
            application
        );

        clearLoadingState();
    }

    applySavedTheme();

    if (backButton) {
        backButton.addEventListener(
            'click',
            () => {
                if (window.history.length > 1) {
                    window.history.back();
                    return;
                }

                window.location.href =
                    'index.html';
            }
        );
    }

    attachAccordionEvents();
    restoreProgress();

    try {
        await loadGuide();
    } catch (error) {
        console.error(
            'OSGuide guide loading error:',
            error
        );

        showError(
            'The guide could not be loaded. Please try again later.'
        );
    }
});
