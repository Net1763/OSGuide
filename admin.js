'use strict';

const SUPABASE_URL =
    'https://rqvicenfdzlleureteis.supabase.co';

const SUPABASE_PUBLISHABLE_KEY =
    'sb_publishable_U64um_oKyNGOzXHQu6PuTg_1R9rSIwA';

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
    isLoadingApplications: false
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
            application.icon_type || 'text';

        elements.applicationPublished.checked =
            application.is_published === true;
    } else {
        elements.applicationModalTitle.textContent =
            'Add application';

        elements.applicationModalDescription.textContent =
            'Enter the application information below.';

        elements.applicationSource.value =
            'F-Droid';

        elements.applicationPlatform.value =
            'Android';

        elements.applicationAdded.value =
            getTodayDateInputValue();

        elements.applicationIconType.value =
            'text';

        elements.applicationPublished.checked =
            true;
    }

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

    elements.applicationForm.reset();
    elements.applicationId.value = '';

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

        is_published:
            elements.applicationPublished.checked
    };
}

function validateApplicationData(applicationData) {
    if (!applicationData.name) {
        return 'Application name is required.';
    }

    if (!applicationData.version) {
        return 'Application version is required.';
    }

    if (!applicationData.size) {
        return 'Application size is required.';
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
        return 'Download URL is required.';
    }

    if (
        !isValidHttpUrl(
            applicationData.download_url
        )
    ) {
        return 'Enter a valid HTTP or HTTPS download URL.';
    }

    return '';
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
        return 'An application with the same unique value already exists.';
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
