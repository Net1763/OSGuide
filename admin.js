// OSGuide Admin Auto F-Droid v2: Package ID enabled
'use strict';

const SUPABASE_URL =
    'https://rqvicenfdzlleureteis.supabase.co';

const SUPABASE_PUBLISHABLE_KEY =
    'sb_publishable_U64um_oKyNG0zXHQu6PuTg_lR9rSIwA';

const supabaseClient = window.supabase.createClient(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY
);

const state = {
    applications: [],
    filteredApplications: [],
    currentUser: null,
    editingApplicationId: null,
    deletingApplicationId: null,
    isLoadingApplications: false,
    fetchedMetadata: null,
    fetchedPackageId: null,
    resolvedSourceMode: 'auto',
    uploadedApkUrl: '',
    uploadedIconUrl: ''
};

const elements = {
    pageLoader: document.getElementById('page-loader'),
    loginView: document.getElementById('login-view'),
    dashboardView: document.getElementById('dashboard-view'),

    loginForm: document.getElementById('login-form'),
    emailInput: document.getElementById('email'),
    passwordInput: document.getElementById('password'),
    togglePasswordButton:
        document.getElementById('toggle-password'),
    loginError: document.getElementById('login-error'),
    loginButton: document.getElementById('login-button'),

    adminEmail: document.getElementById('admin-email'),
    logoutButton: document.getElementById('logout-button'),

    sidebar: document.getElementById('sidebar'),
    sidebarOverlay:
        document.getElementById('sidebar-overlay'),
    openSidebarButton:
        document.getElementById('open-sidebar'),
    closeSidebarButton:
        document.getElementById('close-sidebar'),

    addApplicationButton:
        document.getElementById('add-application-button'),
    emptyAddApplicationButton:
        document.getElementById('empty-add-application'),

    totalApplications:
        document.getElementById('total-applications'),
    publishedApplications:
        document.getElementById('published-applications'),
    unpublishedApplications:
        document.getElementById('unpublished-applications'),
    totalCategories:
        document.getElementById('total-categories'),

    applicationSearch:
        document.getElementById('application-search'),
    publicationFilter:
        document.getElementById('publication-filter'),
    categoryFilter:
        document.getElementById('category-filter'),
    refreshApplicationsButton:
        document.getElementById('refresh-applications'),

    applicationsLoading:
        document.getElementById('applications-loading'),
    applicationsError:
        document.getElementById('applications-error'),
    applicationsErrorMessage:
        document.getElementById('applications-error-message'),
    retryApplicationsButton:
        document.getElementById('retry-applications'),
    applicationsEmpty:
        document.getElementById('applications-empty'),
    applicationsTableWrapper:
        document.getElementById('applications-table-wrapper'),
    applicationsTableBody:
        document.getElementById('applications-table-body'),
    applicationsMobileList:
        document.getElementById('applications-mobile-list'),

    applicationModal:
        document.getElementById('application-modal'),
    applicationModalTitle:
        document.getElementById('application-modal-title'),
    applicationModalDescription:
        document.getElementById(
            'application-modal-description'
        ),
    closeApplicationModalButton:
        document.getElementById('close-application-modal'),
    cancelApplicationButton:
        document.getElementById('cancel-application'),

    applicationForm:
        document.getElementById('application-form'),
    applicationId:
        document.getElementById('application-id'),
    applicationName:
        document.getElementById('application-name'),
    applicationSlug:
        document.getElementById('application-slug'),
    applicationPackageId:
        document.getElementById('application-package-id'),
    fetchFdroidMetadataButton:
        document.getElementById('fetch-app-metadata'),
    fdroidMetadataStatus:
        document.getElementById('app-metadata-status'),
    sourceMode:
        document.getElementById('application-source-mode'),
    repositoryUrl:
        document.getElementById('application-repository-url'),
    repositoryGroup:
        document.getElementById('github-repository-group'),
    resolvedPreview:
        document.getElementById('resolved-app-preview'),
    resolvedIcon:
        document.getElementById('resolved-app-icon'),
    resolvedIconFallback:
        document.getElementById('resolved-app-icon-fallback'),
    resolvedName:
        document.getElementById('resolved-app-name'),
    resolvedSource:
        document.getElementById('resolved-app-source'),
    resolvedTechnical:
        document.getElementById('resolved-app-technical'),
    resolvedHealth:
        document.getElementById('resolved-app-health'),
    directApkStatus:
        document.getElementById('direct-apk-status'),
    iconStatus:
        document.getElementById('icon-status'),
    apkFile:
        document.getElementById('application-apk-file'),
    iconFile:
        document.getElementById('application-icon-file'),
    manualDownloadUrl:
        document.getElementById('manual-download-url'),
    manualImageUrl:
        document.getElementById('manual-image-url'),
    validationChecklist:
        document.getElementById('validation-checklist'),
    applicationVersion:
        document.getElementById('application-version'),
    applicationSize:
        document.getElementById('application-size'),
    applicationCategory:
        document.getElementById('application-category'),
    applicationSource:
        document.getElementById('application-source'),
    applicationLicense:
        document.getElementById('application-license'),
    applicationPlatform:
        document.getElementById('application-platform'),
    applicationAdded:
        document.getElementById('application-added'),
    applicationDescription:
        document.getElementById('application-description'),
    applicationLongDescription:
        document.getElementById(
            'application-long-description'
        ),
    applicationDownloadUrl:
        document.getElementById('application-download-url'),
    applicationIconType:
        document.getElementById('application-icon-type'),
    applicationImageUrlGroup:
        null,
    applicationImageUrl:
        document.getElementById('application-image-url'),
    applicationPublished:
        document.getElementById('application-published'),
    applicationFormError:
        document.getElementById('application-form-error'),
    saveApplicationButton:
        document.getElementById('save-application'),

    deleteModal:
        document.getElementById('delete-modal'),
    deleteApplicationName:
        document.getElementById('delete-application-name'),
    closeDeleteModalButton:
        document.getElementById('close-delete-modal'),
    cancelDeleteButton:
        document.getElementById('cancel-delete'),
    confirmDeleteButton:
        document.getElementById('confirm-delete'),

    toastContainer:
        document.getElementById('toast-container')
};

document.addEventListener(
    'DOMContentLoaded',
    initializeAdminPanel
);

async function initializeAdminPanel() {
    bindEventListeners();

    try {
        const {
            data: { session },
            error
        } = await supabaseClient.auth.getSession();

        if (error) {
            throw error;
        }

        if (session?.user) {
            await showDashboard(session.user);
        } else {
            showLoginView();
        }
    } catch (error) {
        console.error(
            'Unable to initialize admin panel:',
            error
        );

        showLoginView();
        showLoginError(
            'Unable to verify your session. Please sign in.'
        );
    } finally {
        hidePageLoader();
    }

    supabaseClient.auth.onAuthStateChange(
        async (event, session) => {
            if (
                event === 'SIGNED_IN' &&
                session?.user
            ) {
                await showDashboard(session.user);
                return;
            }

            if (event === 'SIGNED_OUT') {
                showLoginView();
            }
        }
    );
}

function bindEventListeners() {
    elements.loginForm.addEventListener(
        'submit',
        handleLogin
    );

    elements.togglePasswordButton.addEventListener(
        'click',
        togglePasswordVisibility
    );

    elements.logoutButton.addEventListener(
        'click',
        handleLogout
    );

    elements.openSidebarButton.addEventListener(
        'click',
        openSidebar
    );

    elements.closeSidebarButton.addEventListener(
        'click',
        closeSidebar
    );

    elements.sidebarOverlay.addEventListener(
        'click',
        closeSidebar
    );

    elements.addApplicationButton.addEventListener(
        'click',
        () => openApplicationModal()
    );

    elements.emptyAddApplicationButton.addEventListener(
        'click',
        () => openApplicationModal()
    );

    elements.refreshApplicationsButton.addEventListener(
        'click',
        loadApplications
    );

    elements.retryApplicationsButton.addEventListener(
        'click',
        loadApplications
    );

    elements.applicationSearch.addEventListener(
        'input',
        applyApplicationFilters
    );

    elements.publicationFilter.addEventListener(
        'change',
        applyApplicationFilters
    );

    elements.categoryFilter.addEventListener(
        'change',
        applyApplicationFilters
    );

    elements.applicationForm.addEventListener(
        'submit',
        handleApplicationSubmit
    );

    elements.fetchFdroidMetadataButton.addEventListener(
        'click',
        fetchAndApplyFdroidMetadata
    );

    if (elements.sourceMode) {
        elements.sourceMode.addEventListener(
            'change',
            handleSourceModeChange
        );
    }

    if (elements.manualDownloadUrl) {
        elements.manualDownloadUrl.addEventListener(
            'input',
            applyManualOverrides
        );
    }

    if (elements.manualImageUrl) {
        elements.manualImageUrl.addEventListener(
            'input',
            applyManualOverrides
        );
    }

    if (elements.apkFile) {
        elements.apkFile.addEventListener(
            'change',
            updateValidationChecklist
        );
    }

    if (elements.iconFile) {
        elements.iconFile.addEventListener(
            'change',
            updateValidationChecklist
        );
    }

    elements.applicationPackageId.addEventListener(
        'input',
        handlePackageIdInput
    );

    elements.applicationName.addEventListener(
        'input',
        handleApplicationNameInput
    );

    elements.applicationSlug.addEventListener(
        'input',
        handleApplicationSlugInput
    );

    elements.closeApplicationModalButton.addEventListener(
        'click',
        closeApplicationModal
    );

    elements.cancelApplicationButton.addEventListener(
        'click',
        closeApplicationModal
    );

    elements.applicationModal
        .querySelector('[data-close-application-modal]')
        .addEventListener(
            'click',
            closeApplicationModal
        );

    elements.closeDeleteModalButton.addEventListener(
        'click',
        closeDeleteModal
    );

    elements.cancelDeleteButton.addEventListener(
        'click',
        closeDeleteModal
    );

    elements.deleteModal
        .querySelector('[data-close-delete-modal]')
        .addEventListener(
            'click',
            closeDeleteModal
        );

    elements.confirmDeleteButton.addEventListener(
        'click',
        handleDeleteApplication
    );

    document.addEventListener(
        'keydown',
        handleGlobalKeydown
    );

    window.addEventListener(
        'resize',
        handleWindowResize
    );
}

async function handleLogin(event) {
    event.preventDefault();

    hideLoginError();

    const email =
        elements.emailInput.value.trim();

    const password =
        elements.passwordInput.value;

    if (!email || !password) {
        showLoginError(
            'Please enter your email and password.'
        );
        return;
    }

    setButtonLoading(
        elements.loginButton,
        true
    );

    try {
        const {
            data,
            error
        } = await supabaseClient.auth.signInWithPassword({
            email,
            password
        });

        if (error) {
            throw error;
        }

        if (!data.user) {
            throw new Error(
                'No authenticated user was returned.'
            );
        }

        elements.loginForm.reset();

        await showDashboard(data.user);

        showToast(
            'Login successful.',
            'success'
        );
    } catch (error) {
        console.error(
            'Admin login failed:',
            error
        );

        showLoginError(
            `DEBUG: ${error.message} (status: ${error.status})`
        );
    } finally {
        setButtonLoading(
            elements.loginButton,
            false
        );
    }
}

async function handleLogout() {
    setButtonLoading(
        elements.logoutButton,
        true
    );

    try {
        const {
            error
        } = await supabaseClient.auth.signOut();

        if (error) {
            throw error;
        }

        state.currentUser = null;
        state.applications = [];
        state.filteredApplications = [];

        showLoginView();

        showToast(
            'You have been logged out.',
            'success'
        );
    } catch (error) {
        console.error(
            'Logout failed:',
            error
        );

        showToast(
            'Unable to log out. Please try again.',
            'error'
        );
    } finally {
        setButtonLoading(
            elements.logoutButton,
            false
        );
    }
}

async function showDashboard(user) {
    state.currentUser = user;

    elements.loginView.hidden = true;
    elements.dashboardView.hidden = false;

    elements.adminEmail.textContent =
        user.email || 'Administrator';

    elements.adminEmail.title =
        user.email || '';

    await loadApplications();
}

function showLoginView() {
    closeSidebar();
    closeApplicationModal();
    closeDeleteModal();

    elements.dashboardView.hidden = true;
    elements.loginView.hidden = false;

    state.currentUser = null;

    window.setTimeout(
        () => {
            elements.emailInput.focus();
        },
        50
    );
}

function hidePageLoader() {
    elements.pageLoader.hidden = true;
}

function togglePasswordVisibility() {
    const isPassword =
        elements.passwordInput.type === 'password';

    elements.passwordInput.type =
        isPassword
            ? 'text'
            : 'password';

    elements.togglePasswordButton.textContent =
        isPassword
            ? 'Hide'
            : 'Show';

    elements.togglePasswordButton.setAttribute(
        'aria-label',
        isPassword
            ? 'Hide password'
            : 'Show password'
    );
}

function openSidebar() {
    elements.sidebar.classList.add('open');
    elements.sidebarOverlay.hidden = false;
    document.body.classList.add('modal-open');
}

function closeSidebar() {
    elements.sidebar.classList.remove('open');
    elements.sidebarOverlay.hidden = true;

    if (
        elements.applicationModal.hidden &&
        elements.deleteModal.hidden
    ) {
        document.body.classList.remove('modal-open');
    }
}

function handleWindowResize() {
    if (window.innerWidth > 860) {
        closeSidebar();
    }
}

function handleGlobalKeydown(event) {
    if (event.key !== 'Escape') {
        return;
    }

    if (!elements.deleteModal.hidden) {
        closeDeleteModal();
        return;
    }

    if (!elements.applicationModal.hidden) {
        closeApplicationModal();
        return;
    }

    closeSidebar();
}

function showLoginError(message) {
    elements.loginError.textContent = message;
    elements.loginError.hidden = false;
}

function hideLoginError() {
    elements.loginError.textContent = '';
    elements.loginError.hidden = true;
}

function getAuthenticationErrorMessage(error) {
    const message =
        String(error?.message || '').toLowerCase();

    if (
        message.includes('invalid login') ||
        message.includes('invalid credentials')
    ) {
        return 'Incorrect email or password.';
    }

    if (message.includes('email not confirmed')) {
        return 'This email address has not been confirmed.';
    }

    if (message.includes('network')) {
        return 'Network error. Check your connection and try again.';
    }

    return 'Login failed. Please check your details and try again.';
}
async function loadApplications() {
    if (state.isLoadingApplications) {
        return;
    }

    state.isLoadingApplications = true;

    showApplicationsLoadingState();

    try {
        const {
            data,
            error
        } = await supabaseClient
            .from('applications')
            .select('*')
            .order('created_at', {
                ascending: false
            });

        if (error) {
            throw error;
        }

        state.applications =
            Array.isArray(data)
                ? data
                : [];

        updateCategoryFilter();
        updateStatistics();
        applyApplicationFilters();
    } catch (error) {
        console.error(
            'Unable to load applications:',
            error
        );

        showApplicationsErrorState(
            getDatabaseErrorMessage(error)
        );
    } finally {
        state.isLoadingApplications = false;
    }
}

function applyApplicationFilters() {
    const searchTerm =
        elements.applicationSearch.value
            .trim()
            .toLowerCase();

    const publicationValue =
        elements.publicationFilter.value;

    const categoryValue =
        elements.categoryFilter.value;

    state.filteredApplications =
        state.applications.filter(
            application => {
                const applicationName =
                    String(
                        application.name || ''
                    ).toLowerCase();

                const matchesSearch =
                    !searchTerm ||
                    applicationName.includes(
                        searchTerm
                    );

                const isPublished =
                    application.is_published === true;

                const matchesPublication =
                    publicationValue === 'all' ||
                    (
                        publicationValue ===
                            'published' &&
                        isPublished
                    ) ||
                    (
                        publicationValue ===
                            'unpublished' &&
                        !isPublished
                    );

                const applicationCategory =
                    String(
                        application.category || ''
                    );

                const matchesCategory =
                    categoryValue === 'all' ||
                    applicationCategory ===
                        categoryValue;

                return (
                    matchesSearch &&
                    matchesPublication &&
                    matchesCategory
                );
            }
        );

    renderApplications();
}

function updateStatistics() {
    const total =
        state.applications.length;

    const published =
        state.applications.filter(
            application =>
                application.is_published === true
        ).length;

    const unpublished =
        total - published;

    const categories =
        new Set(
            state.applications
                .map(
                    application =>
                        String(
                            application.category || ''
                        ).trim()
                )
                .filter(Boolean)
        );

    elements.totalApplications.textContent =
        String(total);

    elements.publishedApplications.textContent =
        String(published);

    elements.unpublishedApplications.textContent =
        String(unpublished);

    elements.totalCategories.textContent =
        String(categories.size);
}

function updateCategoryFilter() {
    const currentValue =
        elements.categoryFilter.value;

    const categories =
        Array.from(
            new Set(
                state.applications
                    .map(
                        application =>
                            String(
                                application.category ||
                                    ''
                            ).trim()
                    )
                    .filter(Boolean)
            )
        ).sort(
            (firstCategory, secondCategory) =>
                firstCategory.localeCompare(
                    secondCategory
                )
        );

    elements.categoryFilter.innerHTML = '';

    const allOption =
        document.createElement('option');

    allOption.value = 'all';
    allOption.textContent = 'All categories';

    elements.categoryFilter.appendChild(
        allOption
    );

    categories.forEach(category => {
        const option =
            document.createElement('option');

        option.value = category;
        option.textContent = category;

        elements.categoryFilter.appendChild(
            option
        );
    });

    const currentValueStillExists =
        currentValue === 'all' ||
        categories.includes(currentValue);

    elements.categoryFilter.value =
        currentValueStillExists
            ? currentValue
            : 'all';
}

function renderApplications() {
    hideAllApplicationStates();

    if (
        state.filteredApplications.length === 0
    ) {
        elements.applicationsEmpty.hidden = false;
        return;
    }

    elements.applicationsTableBody.innerHTML = '';
    elements.applicationsMobileList.innerHTML = '';

    state.filteredApplications.forEach(
        application => {
            elements.applicationsTableBody
                .appendChild(
                    createApplicationTableRow(
                        application
                    )
                );

            elements.applicationsMobileList
                .appendChild(
                    createApplicationMobileCard(
                        application
                    )
                );
        }
    );

    elements.applicationsTableWrapper.hidden =
        false;

    elements.applicationsMobileList.hidden =
        false;
}

function createApplicationTableRow(application) {
    const row =
        document.createElement('tr');

    const nameCell =
        document.createElement('td');

    const nameWrapper =
        document.createElement('div');

    const nameStrong =
        document.createElement('strong');

    const descriptionSmall =
        document.createElement('small');

    nameWrapper.className =
        'application-name-cell';

    nameStrong.textContent =
        application.name || 'Unnamed application';

    descriptionSmall.textContent =
        application.description || '';

    nameWrapper.append(
        nameStrong,
        descriptionSmall
    );

    nameCell.appendChild(nameWrapper);

    const versionCell =
        document.createElement('td');

    versionCell.textContent =
        application.version || '—';

    const categoryCell =
        document.createElement('td');

    categoryCell.textContent =
        application.category || '—';

    const sizeCell =
        document.createElement('td');

    sizeCell.textContent =
        application.size || '—';

    const statusCell =
        document.createElement('td');

    statusCell.appendChild(
        createStatusBadge(
            application.is_published === true
        )
    );

    const addedCell =
        document.createElement('td');

    addedCell.textContent =
        formatApplicationDate(
            application.added ||
            application.created_at
        );

    const actionsCell =
        document.createElement('td');

    actionsCell.appendChild(
        createApplicationActions(
            application
        )
    );

    row.append(
        nameCell,
        versionCell,
        categoryCell,
        sizeCell,
        statusCell,
        addedCell,
        actionsCell
    );

    return row;
}

function createApplicationMobileCard(application) {
    const card =
        document.createElement('article');

    card.className = 'application-card';

    const header =
        document.createElement('div');

    header.className =
        'application-card-header';

    const title =
        document.createElement('h3');

    title.className =
        'application-card-title';

    title.textContent =
        application.name ||
        'Unnamed application';

    header.append(
        title,
        createStatusBadge(
            application.is_published === true
        )
    );

    const meta =
        document.createElement('div');

    meta.className =
        'application-card-meta';

    meta.append(
        createMetaLine(
            'Version',
            application.version || '—'
        ),
        createMetaLine(
            'Category',
            application.category || '—'
        ),
        createMetaLine(
            'Size',
            application.size || '—'
        ),
        createMetaLine(
            'Added',
            formatApplicationDate(
                application.added ||
                application.created_at
            )
        )
    );

    const actions =
        createApplicationActions(
            application
        );

    actions.classList.add(
        'application-card-actions'
    );

    card.append(
        header,
        meta,
        actions
    );

    return card;
}

function createMetaLine(label, value) {
    const line =
        document.createElement('div');

    const labelElement =
        document.createElement('strong');

    const valueElement =
        document.createElement('span');

    labelElement.textContent =
        `${label}: `;

    valueElement.textContent = value;

    line.append(
        labelElement,
        valueElement
    );

    return line;
}

function createStatusBadge(isPublished) {
    const badge =
        document.createElement('span');

    badge.className =
        `status-badge ${
            isPublished
                ? 'published'
                : 'unpublished'
        }`;

    badge.textContent =
        isPublished
            ? 'Published'
            : 'Unpublished';

    return badge;
}

function createApplicationActions(application) {
    const actions =
        document.createElement('div');

    actions.className = 'table-actions';

    const editButton =
        document.createElement('button');

    editButton.type = 'button';
    editButton.className =
        'action-button edit';
    editButton.textContent = 'Edit';
    editButton.setAttribute(
        'aria-label',
        `Edit ${application.name || 'application'}`
    );

    editButton.addEventListener(
        'click',
        () => {
            openApplicationModal(
                application
            );
        }
    );

    const deleteButton =
        document.createElement('button');

    deleteButton.type = 'button';
    deleteButton.className =
        'action-button delete';
    deleteButton.textContent = 'Delete';
    deleteButton.setAttribute(
        'aria-label',
        `Delete ${application.name || 'application'}`
    );

    deleteButton.addEventListener(
        'click',
        () => {
            openDeleteModal(
                application
            );
        }
    );

    actions.append(
        editButton,
        deleteButton
    );

    return actions;
}

function showApplicationsLoadingState() {
    hideAllApplicationStates();

    elements.applicationsLoading.hidden =
        false;
}

function showApplicationsErrorState(message) {
    hideAllApplicationStates();

    elements.applicationsErrorMessage.textContent =
        message;

    elements.applicationsError.hidden =
        false;
}

function hideAllApplicationStates() {
    elements.applicationsLoading.hidden =
        true;

    elements.applicationsError.hidden =
        true;

    elements.applicationsEmpty.hidden =
        true;

    elements.applicationsTableWrapper.hidden =
        true;

    elements.applicationsMobileList.hidden =
        true;
}

function normalizePackageId(value) {
    return String(value || '')
        .trim()
        .toLowerCase();
}

function isValidPackageId(value) {
    return /^[a-z0-9_]+(?:\.[a-z0-9_]+)+$/.test(value);
}

function handlePackageIdInput() {
    const packageId = normalizePackageId(
        elements.applicationPackageId.value
    );

    elements.applicationPackageId.value = packageId;

    if (state.fetchedPackageId !== packageId) {
        state.fetchedMetadata = null;
        state.fetchedPackageId = null;
        elements.applicationVersion.value = '';
        elements.applicationSize.value = '';
        elements.applicationDownloadUrl.value = '';
        elements.applicationImageUrl.value = '';
        elements.applicationSource.value = '';
        setMetadataStatus('', '');
    }

    updateValidationChecklist();
}

function setMetadataStatus(message, type = 'info') {
    if (!message) {
        elements.fdroidMetadataStatus.textContent = '';
        elements.fdroidMetadataStatus.className = 'metadata-status';
        elements.fdroidMetadataStatus.hidden = true;
        return;
    }

    elements.fdroidMetadataStatus.textContent = message;
    elements.fdroidMetadataStatus.className =
        `metadata-status ${type}`;
    elements.fdroidMetadataStatus.hidden = false;
}

async function fetchAndApplyFdroidMetadata() {
    hideApplicationFormError();

    const packageId = normalizePackageId(
        elements.applicationPackageId.value
    );

    const applicationName =
        elements.applicationName.value.trim();

    if (!applicationName) {
        showApplicationFormError(
            'Enter the application name first.'
        );
        elements.applicationName.focus();
        return null;
    }

    if (!isValidPackageId(packageId)) {
        showApplicationFormError(
            'Enter a valid Android Package ID, for example com.example.app.'
        );
        elements.applicationPackageId.focus();
        return null;
    }

    const sourceMode =
        elements.sourceMode?.value || 'auto';

    const repositoryUrl =
        elements.repositoryUrl?.value.trim() || '';

    setButtonLoading(
        elements.fetchFdroidMetadataButton,
        true
    );

    setMetadataStatus(
        'OSGuide is resolving the best available source…',
        'loading'
    );

    try {
        let data = null;
        let error = null;

        const genericResult =
            await supabaseClient.functions.invoke(
                'fetch-app-metadata',
                {
                    body: {
                        name: applicationName,
                        packageId,
                        sourceMode,
                        repositoryUrl
                    }
                }
            );

        data = genericResult.data;
        error = genericResult.error;

        /*
         * Compatibility fallback:
         * before fetch-app-metadata is deployed, existing F-Droid
         * applications keep working with the old Edge Function.
         */
        if (
            error &&
            (
                sourceMode === 'auto' ||
                sourceMode === 'fdroid'
            )
        ) {
            const fallbackResult =
                await supabaseClient.functions.invoke(
                    'fetch-fdroid-metadata',
                    {
                        body: {
                            packageId
                        }
                    }
                );

            if (!fallbackResult.error &&
                fallbackResult.data?.ok &&
                fallbackResult.data?.metadata
            ) {
                data = {
                    ok: true,
                    source: 'Auto',
                    provider: 'fdroid',
                    metadata: fallbackResult.data.metadata
                };
                error = null;
            }
        }

        if (error) {
            throw error;
        }

        if (!data?.ok || !data?.metadata) {
            throw new Error(
                data?.error ||
                'No usable application metadata was returned.'
            );
        }

        const metadata = data.metadata;
        const resolvedSource =
            metadata.source ||
            data.source ||
            (
                data.provider === 'google-play'
                    ? 'Google Play'
                    : data.provider === 'github'
                        ? 'GitHub'
                        : 'F-Droid'
            );

        state.fetchedMetadata = metadata;
        state.fetchedPackageId = packageId;
        state.resolvedSourceMode =
            data.provider || sourceMode;

        elements.applicationPackageId.value =
            packageId;

        elements.applicationVersion.value =
            metadata.version || 'Latest';

        elements.applicationSize.value =
            metadata.size || 'Varies';

        elements.applicationDownloadUrl.value =
            metadata.downloadUrl || '';

        elements.applicationImageUrl.value =
            metadata.imageUrl || '';

        elements.applicationIconType.value =
            metadata.imageUrl ? 'image' : 'default';

        elements.applicationSource.value =
            resolvedSource;

        if (
            !elements.applicationName.value.trim() &&
            metadata.name
        ) {
            elements.applicationName.value =
                metadata.name;
        }

        if (
            !elements.applicationDescription.value.trim() &&
            metadata.description
        ) {
            elements.applicationDescription.value =
                String(metadata.description).slice(0, 300);
        }

        if (
            !elements.applicationLongDescription.value.trim() &&
            metadata.longDescription
        ) {
            elements.applicationLongDescription.value =
                String(metadata.longDescription).slice(0, 3000);
        }

        if (
            !elements.applicationLicense.value.trim() &&
            metadata.license
        ) {
            elements.applicationLicense.value =
                metadata.license;
        }

        handleApplicationNameInput();
        updateResolvedPreview();
        updateValidationChecklist();

        if (metadata.downloadUrl) {
            setMetadataStatus(
                `Ready: ${resolvedSource} returned a direct APK and app metadata.`,
                'success'
            );
        } else {
            setMetadataStatus(
                `${resolvedSource} metadata found. No verified direct APK was returned, so upload the APK below to host it with OSGuide.`,
                'info'
            );
        }

        return metadata;
    } catch (error) {
        console.error(
            'Unable to resolve application metadata:',
            error
        );

        const message =
            error?.context?.body?.error ||
            error?.message ||
            'Unable to resolve application metadata.';

        state.fetchedMetadata = null;
        state.fetchedPackageId = null;

        setMetadataStatus(
            message,
            'error'
        );

        showApplicationFormError(
            message
        );

        updateValidationChecklist();
        return null;
    } finally {
        setButtonLoading(
            elements.fetchFdroidMetadataButton,
            false
        );
    }
}


function handleSourceModeChange() {
    const sourceMode =
        elements.sourceMode?.value || 'auto';

    if (elements.repositoryGroup) {
        elements.repositoryGroup.hidden =
            sourceMode !== 'github';
    }

    state.fetchedMetadata = null;
    state.fetchedPackageId = null;
    state.uploadedApkUrl = '';
    state.uploadedIconUrl = '';

    setMetadataStatus('', '');
    updateValidationChecklist();
}

function applyManualOverrides() {
    const manualDownloadUrl =
        elements.manualDownloadUrl?.value.trim() || '';

    const manualImageUrl =
        elements.manualImageUrl?.value.trim() || '';

    if (manualDownloadUrl) {
        elements.applicationDownloadUrl.value =
            manualDownloadUrl;
    }

    if (manualImageUrl) {
        elements.applicationImageUrl.value =
            manualImageUrl;
        elements.applicationIconType.value = 'image';
    }

    updateResolvedPreview();
    updateValidationChecklist();
}

function setValidationCheck(
    checkName,
    ready,
    readyText,
    pendingText
) {
    if (!elements.validationChecklist) {
        return;
    }

    const row =
        elements.validationChecklist.querySelector(
            `[data-check="${checkName}"]`
        );

    if (!row) {
        return;
    }

    row.classList.toggle(
        'is-ready',
        ready
    );

    row.classList.toggle(
        'is-pending',
        !ready
    );

    const value =
        row.querySelector('strong');

    if (value) {
        value.textContent =
            ready
                ? readyText
                : pendingText;
    }
}

function updateResolvedPreview() {
    if (!elements.resolvedPreview) {
        return;
    }

    const name =
        elements.applicationName.value.trim();

    const source =
        elements.applicationSource.value.trim();

    const version =
        elements.applicationVersion.value.trim();

    const size =
        elements.applicationSize.value.trim();

    const imageUrl =
        elements.applicationImageUrl.value.trim();

    const hasData =
        Boolean(
            name ||
            source ||
            version ||
            imageUrl
        );

    elements.resolvedPreview.hidden =
        !hasData;

    if (!hasData) {
        return;
    }

    elements.resolvedName.textContent =
        name || 'Application';

    elements.resolvedSource.textContent =
        source
            ? `Source: ${source}`
            : 'Source pending';

    elements.resolvedTechnical.textContent =
        [
            version
                ? `Version ${version}`
                : '',
            size || ''
        ]
            .filter(Boolean)
            .join(' · ') ||
        'Technical metadata pending';

    if (imageUrl) {
        elements.resolvedIcon.src =
            imageUrl;

        elements.resolvedIcon.alt =
            `${name || 'Application'} icon`;

        elements.resolvedIcon.hidden =
            false;

        elements.resolvedIconFallback.hidden =
            true;

        elements.resolvedIcon.onerror = () => {
            elements.resolvedIcon.hidden = true;
            elements.resolvedIconFallback.hidden = false;
            if (elements.iconStatus) {
                elements.iconStatus.textContent =
                    'Needs fallback';
            }
        };
    } else {
        elements.resolvedIcon.hidden = true;
        elements.resolvedIconFallback.hidden = false;
    }

    const hasApk =
        Boolean(
            elements.applicationDownloadUrl.value.trim() ||
            elements.apkFile?.files?.[0]
        );

    elements.resolvedHealth.textContent =
        hasApk
            ? 'Ready'
            : 'Needs APK';

    elements.resolvedHealth.classList.toggle(
        'is-ready',
        hasApk
    );
}

function updateValidationChecklist() {
    const packageId =
        normalizePackageId(
            elements.applicationPackageId.value
        );

    const identityReady =
        Boolean(
            elements.applicationName.value.trim() &&
            isValidPackageId(packageId)
        );

    const metadataReady =
        Boolean(
            elements.applicationVersion.value.trim() &&
            elements.applicationSize.value.trim() &&
            elements.applicationSource.value.trim()
        );

    const apkReady =
        Boolean(
            elements.applicationDownloadUrl.value.trim() ||
            elements.apkFile?.files?.[0]
        );

    const iconReady =
        Boolean(
            elements.applicationImageUrl.value.trim() ||
            elements.iconFile?.files?.[0]
        );

    setValidationCheck(
        'identity',
        identityReady,
        'Ready',
        'Name + Package ID'
    );

    setValidationCheck(
        'metadata',
        metadataReady,
        'Ready',
        'Resolve data'
    );

    setValidationCheck(
        'apk',
        apkReady,
        'Ready',
        'Direct APK or upload'
    );

    setValidationCheck(
        'icon',
        iconReady,
        'Ready',
        'Resolve or upload'
    );

    if (elements.directApkStatus) {
        elements.directApkStatus.textContent =
            elements.applicationDownloadUrl.value.trim()
                ? 'Verified URL ready'
                : elements.apkFile?.files?.[0]
                    ? 'Will upload to OSGuide'
                    : 'APK required';
    }

    if (elements.iconStatus) {
        elements.iconStatus.textContent =
            elements.applicationImageUrl.value.trim()
                ? 'Resolved'
                : elements.iconFile?.files?.[0]
                    ? 'Will upload'
                    : 'Icon required';
    }

    updateResolvedPreview();
}

async function uploadAdminFile(
    bucket,
    file,
    packageId,
    kind
) {
    if (!file) {
        return '';
    }

    const safePackageId =
        packageId.replace(
            /[^a-z0-9._-]/gi,
            '-'
        );

    const extension =
        String(file.name || '')
            .split('.')
            .pop()
            .toLowerCase() ||
        (
            kind === 'apk'
                ? 'apk'
                : 'png'
        );

    const filePath =
        `${safePackageId}/${kind}-${Date.now()}.${extension}`;

    const {
        error
    } = await supabaseClient
        .storage
        .from(bucket)
        .upload(
            filePath,
            file,
            {
                upsert: false,
                contentType:
                    file.type ||
                    (
                        kind === 'apk'
                            ? 'application/vnd.android.package-archive'
                            : 'application/octet-stream'
                    )
            }
        );

    if (error) {
        throw error;
    }

    const {
        data
    } = supabaseClient
        .storage
        .from(bucket)
        .getPublicUrl(
            filePath,
            kind === 'apk'
                ? { download: true }
                : undefined
        );

    return data?.publicUrl || '';
}

async function prepareHostedFilesBeforeSave() {
    const packageId =
        normalizePackageId(
            elements.applicationPackageId.value
        );

    const apkFile =
        elements.apkFile?.files?.[0] || null;

    const iconFile =
        elements.iconFile?.files?.[0] || null;

    if (
        !elements.applicationDownloadUrl.value.trim() &&
        apkFile
    ) {
        setMetadataStatus(
            'Uploading APK to OSGuide Storage…',
            'loading'
        );

        const apkUrl =
            await uploadAdminFile(
                'osguide-apks',
                apkFile,
                packageId,
                'app'
            );

        elements.applicationDownloadUrl.value =
            apkUrl;

        elements.applicationSource.value =
            'OSGuide Hosted';

        state.uploadedApkUrl =
            apkUrl;
    }

    if (
        !elements.applicationImageUrl.value.trim() &&
        iconFile
    ) {
        setMetadataStatus(
            'Uploading application icon…',
            'loading'
        );

        const iconUrl =
            await uploadAdminFile(
                'osguide-icons',
                iconFile,
                packageId,
                'icon'
            );

        elements.applicationImageUrl.value =
            iconUrl;

        elements.applicationIconType.value =
            'image';

        state.uploadedIconUrl =
            iconUrl;
    }

    updateValidationChecklist();
}

function openApplicationModal(
    application = null
) {
    hideApplicationFormError();

    elements.applicationForm.reset();

    state.editingApplicationId =
        application?.id || null;

    elements.applicationId.value =
        application?.id || '';

    if (application) {
        elements.applicationModalTitle.textContent =
            'Edit application';

        elements.applicationModalDescription.textContent =
            'Update the application information below.';

        elements.applicationName.value =
            application.name || '';

        elements.applicationSlug.value =
            application.slug ||
            createSlug(application.name || '');

        elements.applicationSlug.dataset.manual =
            application.slug
                ? 'true'
                : 'false';

        elements.applicationPackageId.value =
            application.package_id || '';

        elements.applicationVersion.value =
            application.version || '';

        elements.applicationSize.value =
            application.size || '';

        elements.applicationCategory.value =
            application.category || '';

        elements.applicationSource.value =
            application.source || 'F-Droid';

        elements.applicationLicense.value =
            application.license || '';

        elements.applicationPlatform.value =
            application.platform || 'Android';

        elements.applicationAdded.value =
            normalizeDateInputValue(
                application.added ||
                application.created_at
            );

        elements.applicationDescription.value =
            application.description || '';

        elements.applicationLongDescription.value =
            application.long_description || '';

        elements.applicationDownloadUrl.value =
            application.download_url || '';

        elements.applicationIconType.value =
            application.icon_type || 'image';

        elements.applicationImageUrl.value =
            application.image_url || '';

        elements.applicationPublished.checked =
            application.is_published === true;
    } else {
        elements.applicationModalTitle.textContent =
            'Add application';

        elements.applicationModalDescription.textContent =
            'Enter the application information below.';

        elements.applicationSlug.value = '';
        elements.applicationSlug.dataset.manual = 'false';
        elements.applicationPackageId.value = '';

        elements.applicationSource.value =
            '';

        elements.applicationPlatform.value =
            'Android';

        elements.applicationAdded.value =
            getTodayDateInputValue();

        elements.applicationIconType.value =
            'image';

        elements.applicationImageUrl.value = '';

        elements.applicationPublished.checked =
            true;
    }

    state.fetchedMetadata = application ? {
        version: application.version || '',
        size: application.size || '',
        downloadUrl: application.download_url || '',
        imageUrl: application.image_url || ''
    } : null;
    state.fetchedPackageId = application?.package_id || null;

    if (application?.package_id) {
        setMetadataStatus(
            'Stored metadata is loaded. Use “Resolve app data” to refresh it.',
            'info'
        );
    } else {
        setMetadataStatus('', '');
    }

    if (elements.sourceMode) {
        elements.sourceMode.value =
            application?.source === 'F-Droid'
                ? 'fdroid'
                : 'auto';
    }

    if (elements.repositoryGroup) {
        elements.repositoryGroup.hidden = true;
    }

    if (elements.manualDownloadUrl) {
        elements.manualDownloadUrl.value = '';
    }

    if (elements.manualImageUrl) {
        elements.manualImageUrl.value = '';
    }

    if (elements.apkFile) {
        elements.apkFile.value = '';
    }

    if (elements.iconFile) {
        elements.iconFile.value = '';
    }

    updateResolvedPreview();
    updateValidationChecklist();

    elements.applicationModal.hidden = false;
    document.body.classList.add('modal-open');

    window.setTimeout(
        () => {
            elements.applicationName.focus();
        },
        50
    );
}

function closeApplicationModal() {
    if (elements.applicationModal.hidden) {
        return;
    }

    elements.applicationModal.hidden = true;

    state.editingApplicationId = null;
    state.fetchedMetadata = null;
    state.fetchedPackageId = null;

    elements.applicationForm.reset();
    elements.applicationId.value = '';
    elements.applicationSlug.dataset.manual = 'false';

    hideApplicationFormError();

    if (
        elements.deleteModal.hidden &&
        !elements.sidebar.classList.contains(
            'open'
        )
    ) {
        document.body.classList.remove(
            'modal-open'
        );
    }
}

function openDeleteModal(application) {
    state.deletingApplicationId =
        application.id;

    elements.deleteApplicationName.textContent =
        application.name ||
        'this application';

    elements.deleteModal.hidden = false;
    document.body.classList.add('modal-open');

    window.setTimeout(
        () => {
            elements.confirmDeleteButton.focus();
        },
        50
    );
}

function closeDeleteModal() {
    if (elements.deleteModal.hidden) {
        return;
    }

    elements.deleteModal.hidden = true;

    state.deletingApplicationId = null;

    elements.deleteApplicationName.textContent =
        'this application';

    if (
        elements.applicationModal.hidden &&
        !elements.sidebar.classList.contains(
            'open'
        )
    ) {
        document.body.classList.remove(
            'modal-open'
        );
    }
}async function handleApplicationSubmit(event) {
    event.preventDefault();

    hideApplicationFormError();

    const packageId = normalizePackageId(
        elements.applicationPackageId.value
    );

    if (!isValidPackageId(packageId)) {
        showApplicationFormError(
            'Enter a valid Android Package ID.'
        );
        return;
    }

    if (
        state.fetchedPackageId !== packageId &&
        !elements.applicationDownloadUrl.value.trim()
    ) {
        const metadata =
            await fetchAndApplyFdroidMetadata();

        if (
            !metadata &&
            !elements.apkFile?.files?.[0]
        ) {
            return;
        }
    }

    try {
        await prepareHostedFilesBeforeSave();
    } catch (error) {
        console.error(
            'Unable to upload OSGuide-hosted files:',
            error
        );

        showApplicationFormError(
            error?.message ||
            'Unable to upload the APK or icon.'
        );
        return;
    }

    const applicationData =
        getApplicationFormData();

    const validationError =
        validateApplicationData(
            applicationData
        );

    if (validationError) {
        showApplicationFormError(
            validationError
        );
        return;
    }

    setButtonLoading(
        elements.saveApplicationButton,
        true
    );

    try {
        let query;

        if (state.editingApplicationId) {
            query = supabaseClient
                .from('applications')
                .update(applicationData)
                .eq(
                    'id',
                    state.editingApplicationId
                );
        } else {
            query = supabaseClient
                .from('applications')
                .insert(applicationData);
        }

        const {
            error
        } = await query;

        if (error) {
            throw error;
        }

        const successMessage =
            state.editingApplicationId
                ? 'Application updated successfully.'
                : 'Application added successfully.';

        closeApplicationModal();

        showToast(
            successMessage,
            'success'
        );

        await loadApplications();
    } catch (error) {
        console.error(
            'Unable to save application:',
            error
        );

        showApplicationFormError(
            getDatabaseErrorMessage(error)
        );
    } finally {
        setButtonLoading(
            elements.saveApplicationButton,
            false
        );
    }
}

function getApplicationFormData() {
    return {
        name:
            elements.applicationName.value.trim(),

        slug:
            normalizeSlug(
                elements.applicationSlug.value
            ),

        package_id:
            normalizePackageId(
                elements.applicationPackageId.value
            ),

        description:
            elements.applicationDescription.value.trim(),

        long_description:
            elements.applicationLongDescription.value.trim() ||
            null,

        version:
            elements.applicationVersion.value.trim(),

        size:
            elements.applicationSize.value.trim(),

        source:
            elements.applicationSource.value.trim(),

        license:
            elements.applicationLicense.value.trim() ||
            null,

        platform:
            elements.applicationPlatform.value.trim() ||
            'Android',

        category:
            elements.applicationCategory.value.trim(),

        added:
            elements.applicationAdded.value,

        download_url:
            elements.applicationDownloadUrl.value.trim(),

        icon_type:
            elements.applicationIconType.value,

        image_url:
            elements.applicationIconType.value === 'image'
                ? elements.applicationImageUrl.value.trim() || null
                : null,

        is_published:
            elements.applicationPublished.checked,

        metadata_status:
            'ready',

        metadata_updated_at:
            new Date().toISOString()
    };
}

function validateApplicationData(applicationData) {
    if (!applicationData.name) {
        return 'Application name is required.';
    }

    if (!applicationData.slug) {
        return 'Slug is required.';
    }

    if (!isValidSlug(applicationData.slug)) {
        return 'Slug may contain only lowercase letters, numbers and hyphens.';
    }

    if (!applicationData.package_id) {
        return 'Android Package ID is required.';
    }

    if (!isValidPackageId(applicationData.package_id)) {
        return 'Enter a valid Android Package ID.';
    }

    if (!applicationData.version) {
        return 'Resolve application data before saving.';
    }

    if (!applicationData.size) {
        return 'APK size is required before publishing.';
    }

    if (!applicationData.category) {
        return 'Application category is required.';
    }

    if (!applicationData.source) {
        return 'Application source is required.';
    }

    if (!applicationData.added) {
        return 'Added date is required.';
    }

    if (!applicationData.description) {
        return 'Short description is required.';
    }

    if (
        applicationData.description.length >
        300
    ) {
        return 'Short description must not exceed 300 characters.';
    }

    if (
        applicationData.long_description &&
        applicationData.long_description.length >
            3000
    ) {
        return 'Full description must not exceed 3000 characters.';
    }

    if (!applicationData.download_url) {
        return 'A direct APK URL or OSGuide-hosted APK is required.';
    }

    if (
        !isValidHttpUrl(
            applicationData.download_url
        )
    ) {
        return 'Enter a valid HTTP or HTTPS download URL.';
    }

    if (
        applicationData.icon_type === 'image' &&
        !applicationData.image_url
    ) {
        return 'Image URL is required when Image URL is selected.';
    }

    if (
        applicationData.image_url &&
        !isValidHttpUrl(applicationData.image_url)
    ) {
        return 'Enter a valid HTTP or HTTPS image URL.';
    }

    return '';
}

function createSlug(value) {
    return normalizeSlug(value);
}

function normalizeSlug(value) {
    return String(value || '')
        .trim()
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .replace(/-{2,}/g, '-');
}

function isValidSlug(value) {
    return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value);
}

function handleApplicationNameInput() {
    if (
        elements.applicationSlug.dataset.manual === 'true'
    ) {
        return;
    }

    elements.applicationSlug.value =
        createSlug(
            elements.applicationName.value
        );

    updateValidationChecklist();
}

function handleApplicationSlugInput() {
    const normalizedValue =
        normalizeSlug(
            elements.applicationSlug.value
        );

    elements.applicationSlug.value =
        normalizedValue;

    elements.applicationSlug.dataset.manual =
        normalizedValue
            ? 'true'
            : 'false';
}

function isValidHttpUrl(value) {
    try {
        const url =
            new URL(value);

        return (
            url.protocol === 'http:' ||
            url.protocol === 'https:'
        );
    } catch {
        return false;
    }
}

function showApplicationFormError(message) {
    elements.applicationFormError.textContent =
        message;

    elements.applicationFormError.hidden =
        false;
}

function hideApplicationFormError() {
    elements.applicationFormError.textContent =
        '';

    elements.applicationFormError.hidden =
        true;
}

async function handleDeleteApplication() {
    if (!state.deletingApplicationId) {
        return;
    }

    setButtonLoading(
        elements.confirmDeleteButton,
        true
    );

    try {
        const {
            error
        } = await supabaseClient
            .from('applications')
            .delete()
            .eq(
                'id',
                state.deletingApplicationId
            );

        if (error) {
            throw error;
        }

        closeDeleteModal();

        showToast(
            'Application deleted successfully.',
            'success'
        );

        await loadApplications();
    } catch (error) {
        console.error(
            'Unable to delete application:',
            error
        );

        showToast(
            getDatabaseErrorMessage(error),
            'error'
        );
    } finally {
        setButtonLoading(
            elements.confirmDeleteButton,
            false
        );
    }
}

function setButtonLoading(
    button,
    isLoading
) {
    if (!button) {
        return;
    }

    const textElement =
        button.querySelector('.button-text');

    const loaderElement =
        button.querySelector('.button-loader');

    button.disabled = isLoading;

    if (textElement) {
        textElement.hidden = isLoading;
    }

    if (loaderElement) {
        loaderElement.hidden = !isLoading;
    }
}

function showToast(
    message,
    type = 'success'
) {
    const toast =
        document.createElement('div');

    toast.className =
        `toast ${type}`;

    toast.setAttribute(
        'role',
        type === 'error'
            ? 'alert'
            : 'status'
    );

    const messageElement =
        document.createElement('span');

    messageElement.textContent =
        message;

    toast.appendChild(
        messageElement
    );

    elements.toastContainer.appendChild(
        toast
    );

    window.setTimeout(
        () => {
            toast.style.opacity = '0';
            toast.style.transform =
                'translateY(10px)';

            window.setTimeout(
                () => {
                    toast.remove();
                },
                220
            );
        },
        4000
    );
}

function formatApplicationDate(value) {
    if (!value) {
        return '—';
    }

    const date =
        new Date(value);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return String(value);
    }

    return new Intl.DateTimeFormat(
        'en',
        {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        }
    ).format(date);
}

function normalizeDateInputValue(value) {
    if (!value) {
        return getTodayDateInputValue();
    }

    const valueString =
        String(value);

    const directDateMatch =
        valueString.match(
            /^\d{4}-\d{2}-\d{2}/
        );

    if (directDateMatch) {
        return directDateMatch[0];
    }

    const date =
        new Date(value);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return getTodayDateInputValue();
    }

    return formatDateForInput(date);
}

function getTodayDateInputValue() {
    return formatDateForInput(
        new Date()
    );
}

function formatDateForInput(date) {
    const year =
        date.getFullYear();

    const month =
        String(
            date.getMonth() + 1
        ).padStart(
            2,
            '0'
        );

    const day =
        String(
            date.getDate()
        ).padStart(
            2,
            '0'
        );

    return `${year}-${month}-${day}`;
}

function getDatabaseErrorMessage(error) {
    const message =
        String(
            error?.message || ''
        ).toLowerCase();

    if (
        message.includes(
            'row-level security'
        ) ||
        message.includes(
            'permission denied'
        )
    ) {
        return 'You do not have permission to perform this action.';
    }

    if (
        message.includes(
            'duplicate'
        ) ||
        error?.code === '23505'
    ) {
        return 'This slug or Package ID is already used by another application.';
    }

    if (
        message.includes(
            'network'
        ) ||
        message.includes(
            'failed to fetch'
        )
    ) {
        return 'Network error. Check your connection and try again.';
    }

    if (
        message.includes(
            'not authenticated'
        ) ||
        message.includes(
            'jwt'
        )
    ) {
        return 'Your session has expired. Please sign in again.';
    }

    return 'An unexpected database error occurred. Please try again.';
}
