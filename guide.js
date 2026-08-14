import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

'use strict';


/* =========================================================
   OSGuide — Guide System V2
   Auth + application loading + LEARN / DO / FIX / REFERENCE
========================================================= */


/* =========================================================
   1. Supabase
========================================================= */

const SUPABASE_URL =
    'https://rqvicenfdzlleureteis.supabase.co';

const SUPABASE_PUBLISHABLE_KEY =
    'sb_publishable_U64um_oKyNG0zXHQu6PuTg_lR9rSIwA';

const supabase =
    createClient(
        SUPABASE_URL,
        SUPABASE_PUBLISHABLE_KEY,
        {
            auth: {
                persistSession: true,
                autoRefreshToken: true,
                detectSessionInUrl: true
            }
        }
    );


/* =========================================================
   2. DOM
========================================================= */

const authGate =
    document.getElementById('guide-auth-gate');

const authStatus =
    document.getElementById('guide-auth-status');

const googleLoginButton =
    document.getElementById('guide-google-login');

const appShell =
    document.getElementById('guide-app-shell');

const guideMain =
    document.getElementById('guide-main');

const appIcon =
    document.getElementById('guide-app-icon');

const appName =
    document.getElementById('guide-app-name');

const appDescription =
    document.getElementById('guide-app-description');

const levelBadge =
    document.getElementById('guide-level-badge');

const sidebarSource =
    document.getElementById('guide-sidebar-source');

const lessonsCount =
    document.getElementById('guide-lessons-count');

const tasksCount =
    document.getElementById('guide-tasks-count');

const fixesCount =
    document.getElementById('guide-fixes-count');

const modeLessonsCount =
    document.getElementById('guide-mode-lessons-count');

const modeTasksCount =
    document.getElementById('guide-mode-tasks-count');

const modeFixesCount =
    document.getElementById('guide-mode-fixes-count');

const progressRing =
    document.getElementById('guide-progress-ring');

const progressPercent =
    document.getElementById('guide-progress-percent');

const progressTitle =
    document.getElementById('guide-progress-title');

const progressSubtitle =
    document.getElementById('guide-progress-subtitle');

const continueButton =
    document.getElementById('guide-continue-button');

const resumeNumber =
    document.getElementById('guide-resume-number');

const resumeTitle =
    document.getElementById('guide-resume-title');

const resumeSection =
    document.getElementById('guide-resume-section');

const resumeProgressBar =
    document.getElementById('guide-resume-progress-bar');

const resumePercent =
    document.getElementById('guide-resume-percent');

const resumeButton =
    document.getElementById('guide-resume-button');

const recentList =
    document.getElementById('guide-recent-list');

const workspaceNumber =
    document.getElementById('guide-workspace-number');

const workspaceTitle =
    document.getElementById('guide-workspace-title');

const workspaceSubtitle =
    document.getElementById('guide-workspace-subtitle');

const workspaceTopButton =
    document.getElementById('guide-workspace-top-button');

const learnWorkspace =
    document.getElementById('guide-learn-workspace');

const doWorkspace =
    document.getElementById('guide-do-workspace');

const fixWorkspace =
    document.getElementById('guide-fix-workspace');

const referenceWorkspace =
    document.getElementById('guide-reference-workspace');

const lessonsNavigation =
    document.getElementById('guide-lessons-navigation');

const mobileLessonsButton =
    document.getElementById('guide-mobile-lessons-button');

const mobileLessonLabel =
    document.getElementById('guide-mobile-lesson-label');

const mobileLessonsMenu =
    document.getElementById('guide-mobile-lessons-menu');

const lessonKicker =
    document.getElementById('guide-lesson-kicker');

const lessonTitle =
    document.getElementById('guide-lesson-title');

const lessonSummary =
    document.getElementById('guide-lesson-summary');

const stepProgressLabel =
    document.getElementById('guide-step-progress-label');

const stepProgressBar =
    document.getElementById('guide-step-progress-bar');

const lessonContent =
    document.getElementById('guide-lesson-content');

const lessonOutline =
    document.getElementById('guide-lesson-outline');

const lessonTip =
    document.getElementById('guide-lesson-tip');

const lessonPrevious =
    document.getElementById('guide-lesson-previous');

const lessonNext =
    document.getElementById('guide-lesson-next');

const markStepDone =
    document.getElementById('guide-mark-step-done');

const tasksNavigation =
    document.getElementById('guide-tasks-navigation');

const taskTitle =
    document.getElementById('guide-task-title');

const taskSummary =
    document.getElementById('guide-task-summary');

const taskLevel =
    document.getElementById('guide-task-level');

const taskTime =
    document.getElementById('guide-task-time');

const taskSteps =
    document.getElementById('guide-task-steps');

const taskResults =
    document.getElementById('guide-task-results');

const taskResources =
    document.getElementById('guide-task-resources');

const taskStartButton =
    document.getElementById('guide-task-start-button');

const fixesNavigation =
    document.getElementById('guide-fixes-navigation');

const fixTitle =
    document.getElementById('guide-fix-title');

const fixTags =
    document.getElementById('guide-fix-tags');

const fixProblem =
    document.getElementById('guide-fix-problem');

const fixCause =
    document.getElementById('guide-fix-cause');

const fixSteps =
    document.getElementById('guide-fix-steps');

const fixRelated =
    document.getElementById('guide-fix-related');

const referenceNavigation =
    document.getElementById('guide-reference-navigation');

const referenceTitle =
    document.getElementById('guide-reference-title');

const referenceSearchInput =
    document.getElementById('guide-reference-search-input');

const referenceTableBody =
    document.getElementById('guide-reference-table-body');

const referenceMobileList =
    document.getElementById('guide-reference-mobile-list');

const globalSearchInput =
    document.getElementById('guide-global-search-input');

const searchResults =
    document.getElementById('guide-search-results');

const accountButton =
    document.getElementById('guide-account-button');

const accountAvatar =
    document.getElementById('guide-account-avatar');

const accountMenu =
    document.getElementById('guide-account-menu');

const accountName =
    document.getElementById('guide-account-name');

const accountEmail =
    document.getElementById('guide-account-email');

const signOutButton =
    document.getElementById('guide-sign-out-button');

const mobileMenuButton =
    document.getElementById('guide-mobile-menu-button');

const mobileDrawerShell =
    document.getElementById('guide-mobile-drawer-shell');

const mobileDrawerBackdrop =
    document.getElementById('guide-mobile-drawer-backdrop');

const mobileDrawerClose =
    document.getElementById('guide-mobile-drawer-close');

const toast =
    document.getElementById('guide-toast');


/* =========================================================
   3. URL
========================================================= */

const params =
    new URLSearchParams(window.location.search);

const appSlug =
    String(
        params.get('slug') ||
        params.get('id') ||
        ''
    )
        .trim()
        .toLowerCase();


/* =========================================================
   4. State
========================================================= */

const state = {
    user: null,
    application: null,
    guide: null,

    mode: 'learn',

    lessonIndex: 0,
    stepIndex: 0,

    taskIndex: 0,
    fixIndex: 0,
    referenceIndex: 0,

    progress: {
        completedSteps: {},
        completedTasks: {},
        feedback: {},
        recentlyViewed: []
    }
};


/* =========================================================
   5. Utilities
========================================================= */

function escapeHTML(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function clamp(value, min, max) {
    return Math.min(
        Math.max(value, min),
        max
    );
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
                fill="#080b0f"
            />
            <text
                x="48"
                y="62"
                text-anchor="middle"
                font-family="Arial, sans-serif"
                font-size="48"
                font-weight="700"
                fill="#ffffff"
            >${escapeHTML(firstLetter)}</text>
        </svg>
    `;

    return (
        'data:image/svg+xml;charset=UTF-8,' +
        encodeURIComponent(svg)
    );
}

function showToast(message) {
    if (!toast) {
        return;
    }

    toast.textContent =
        message;

    toast.hidden =
        false;

    clearTimeout(
        showToast.timer
    );

    showToast.timer =
        setTimeout(
            () => {
                toast.hidden = true;
            },
            2200
        );
}

async function copyText(value) {
    try {
        await navigator.clipboard.writeText(
            value
        );

        showToast(
            'Copied to clipboard.'
        );
    } catch {
        showToast(
            'Could not copy automatically.'
        );
    }
}

function scrollWorkspaceIntoView() {
    const header =
        document.querySelector(
            '.guide-workspace-header'
        );

    if (!header) {
        return;
    }

    const top =
        header.getBoundingClientRect().top +
        window.scrollY -
        76;

    window.scrollTo({
        top,
        behavior: 'smooth'
    });
}


/* =========================================================
   6. Content Library — Termux
========================================================= */

const TERMUX_GUIDE = {
    level: 'Beginner to Advanced',

    lessons: [
        {
            id: 'introduction',
            section: 'Foundations',
            title: 'Introduction',
            summary:
                'Understand what Termux is, what it can do and how this learning path is organized.',
            tip:
                'You can open any lesson at any time. The order is recommended, not forced.',
            steps: [
                {
                    title: 'What Termux gives you',
                    body:
                        'Termux provides a Linux-like terminal environment on Android. You can work with commands, files, packages and developer tools directly from your phone.',
                    why:
                        'The terminal is not a separate operating system. It is an Android app that gives you command-line tools inside its own environment.'
                },
                {
                    title: 'How this guide works',
                    body:
                        'Use LEARN for structured lessons, DO for practical goals, FIX for troubleshooting and REFERENCE when you need a quick answer.',
                    why:
                        'Different situations need different kinds of documentation. A learning path should not slow you down when you only need one command.'
                }
            ]
        },

        {
            id: 'terminal-basics',
            section: 'Foundations',
            title: 'What is a terminal?',
            summary:
                'Learn how commands, prompts and output work before you start changing files or installing packages.',
            tip:
                'Read a command before running it. Small typing differences can change what a command does.',
            steps: [
                {
                    title: 'Recognize the prompt',
                    body:
                        'The prompt is the area where Termux waits for your next command. You type after it and press Enter.',
                    code:
                        'echo "Hello from Termux"',
                    output:
                        'Hello from Termux',
                    why:
                        'The echo command prints text. It is a safe first command because it changes nothing.'
                },
                {
                    title: 'Commands and arguments',
                    body:
                        'Many commands are followed by extra values called arguments. Arguments tell a command what to act on.',
                    code:
                        'ls -la',
                    why:
                        'Here, ls is the command and -la changes how the directory contents are displayed.'
                }
            ]
        },

        {
            id: 'first-commands',
            section: 'Foundations',
            title: 'Your first commands',
            summary:
                'Use basic navigation commands to understand where you are and what files are around you.',
            tip:
                'Press Tab to autocomplete paths and command names when possible.',
            steps: [
                {
                    title: 'Print working directory',
                    body:
                        'This command shows the full path of your current directory.',
                    code:
                        'pwd',
                    output:
                        '/data/data/com.termux/files/home',
                    why:
                        'Every terminal session has a current directory. Many commands work relative to that location.'
                },
                {
                    title: 'List files',
                    body:
                        'List the visible files and directories in your current location.',
                    code:
                        'ls',
                    why:
                        'Listing first helps you inspect a location before you move, copy, rename or delete anything.'
                },
                {
                    title: 'Change directory',
                    body:
                        'Move into another directory by giving cd a path.',
                    code:
                        'cd /sdcard',
                    why:
                        'cd changes the directory your next commands will operate from.'
                },
                {
                    title: 'View file content',
                    body:
                        'Use cat for small text files when you need to quickly see their content.',
                    code:
                        'cat README.txt',
                    why:
                        'cat sends the file content to the terminal output without opening a full editor.'
                },
                {
                    title: 'Clear the screen',
                    body:
                        'Clean the terminal view without deleting your command history.',
                    code:
                        'clear',
                    why:
                        'clear only redraws the terminal. It does not remove files or uninstall anything.'
                },
                {
                    title: 'Review the result',
                    body:
                        'You now know how to identify your location, inspect files, move between directories and read a simple text file.',
                    why:
                        'These navigation skills are the foundation for almost every practical Termux workflow.'
                }
            ]
        },

        {
            id: 'files-directories',
            section: 'Foundations',
            title: 'Files and directories',
            summary:
                'Create, copy, move and remove files while understanding what each command changes.',
            tip:
                'Be careful with rm. Deleted files usually do not go to a recycle bin.',
            steps: [
                {
                    title: 'Create a directory',
                    body:
                        'Create a new folder for a project or group of files.',
                    code:
                        'mkdir my-project',
                    why:
                        'Keeping work in dedicated folders makes commands safer and projects easier to manage.'
                },
                {
                    title: 'Create a file',
                    body:
                        'Create an empty text file inside your project.',
                    code:
                        'touch my-project/README.txt'
                },
                {
                    title: 'Copy a file',
                    body:
                        'Duplicate a file while keeping the original.',
                    code:
                        'cp my-project/README.txt my-project/README-copy.txt'
                },
                {
                    title: 'Move or rename',
                    body:
                        'Use mv to move a file to another location or give it a new name.',
                    code:
                        'mv my-project/README-copy.txt my-project/NOTES.txt'
                }
            ]
        },

        {
            id: 'permissions',
            section: 'Foundations',
            title: 'Permissions basics',
            summary:
                'Understand why Android and Linux permissions affect files and commands.',
            tip:
                'Do not grant broad permissions unless a task really needs them.',
            steps: [
                {
                    title: 'Enable shared storage access',
                    body:
                        'Termux can request access to shared Android storage when you need to work with files outside its private directory.',
                    code:
                        'termux-setup-storage',
                    why:
                        'Android isolates apps by default. Shared storage access must be requested explicitly.'
                },
                {
                    title: 'Inspect file permissions',
                    body:
                        'Use ls with the long format to inspect ownership and permission bits.',
                    code:
                        'ls -l'
                }
            ]
        },

        {
            id: 'packages',
            section: 'Linux tools',
            title: 'Package management',
            summary:
                'Update package information, search available tools and install software safely.',
            tip:
                'Run pkg update before troubleshooting a package that appears to be missing.',
            steps: [
                {
                    title: 'Update package lists',
                    body:
                        'Refresh the information Termux has about available packages.',
                    code:
                        'pkg update'
                },
                {
                    title: 'Upgrade installed packages',
                    body:
                        'Install newer versions of packages already on your device.',
                    code:
                        'pkg upgrade'
                },
                {
                    title: 'Search packages',
                    body:
                        'Search package names and descriptions.',
                    code:
                        'pkg search git'
                },
                {
                    title: 'Install a package',
                    body:
                        'Install Git from the configured Termux repositories.',
                    code:
                        'pkg install git'
                }
            ]
        },

        {
            id: 'environment',
            section: 'Linux tools',
            title: 'Environment variables',
            summary:
                'Learn how environment variables influence commands and tools.',
            tip:
                'Avoid editing shell configuration files until you understand the line you are adding.',
            steps: [
                {
                    title: 'Inspect PATH',
                    body:
                        'PATH tells your shell where to look for executable commands.',
                    code:
                        'echo $PATH'
                },
                {
                    title: 'Inspect HOME',
                    body:
                        'HOME points to your main Termux user directory.',
                    code:
                        'echo $HOME'
                }
            ]
        },

        {
            id: 'pipes-redirection',
            section: 'Linux tools',
            title: 'Pipes and redirection',
            summary:
                'Connect commands together and send output into files.',
            tip:
                'Use > carefully because it replaces the target file content.',
            steps: [
                {
                    title: 'Pipe output',
                    body:
                        'Send the output of one command into another.',
                    code:
                        'ls | sort'
                },
                {
                    title: 'Write output to a file',
                    body:
                        'Save command output into a text file.',
                    code:
                        'pwd > current-path.txt'
                }
            ]
        },

        {
            id: 'package-advanced',
            section: 'Advanced',
            title: 'Advanced package tips',
            summary:
                'Inspect packages, remove unused tools and recover from repository issues.',
            tip:
                'Keep important projects backed up before large environment changes.',
            steps: [
                {
                    title: 'Show installed packages',
                    body:
                        'Inspect packages currently installed in your Termux environment.',
                    code:
                        'pkg list-installed'
                },
                {
                    title: 'Remove a package',
                    body:
                        'Uninstall a package you no longer need.',
                    code:
                        'pkg uninstall package-name'
                }
            ]
        },

        {
            id: 'shortcuts',
            section: 'Advanced',
            title: 'Useful shortcuts',
            summary:
                'Work faster with shell navigation and command history.',
            tip:
                'Learning a few shortcuts saves more time than memorizing dozens of commands.',
            steps: [
                {
                    title: 'Reuse command history',
                    body:
                        'Use the terminal history controls to bring back commands instead of typing them again.'
                },
                {
                    title: 'Autocomplete',
                    body:
                        'Use Tab to autocomplete commands and file names where possible.'
                }
            ]
        },

        {
            id: 'shell-scripting',
            section: 'Advanced',
            title: 'Shell scripting',
            summary:
                'Put multiple commands into a reusable script.',
            tip:
                'Start scripts small. Add error handling only after the basic workflow is correct.',
            steps: [
                {
                    title: 'Create a script',
                    body:
                        'Create a simple shell script file.',
                    code:
                        'nano hello.sh'
                },
                {
                    title: 'Make it executable',
                    body:
                        'Give the file execute permission.',
                    code:
                        'chmod +x hello.sh'
                },
                {
                    title: 'Run it',
                    body:
                        'Execute the script from the current directory.',
                    code:
                        './hello.sh'
                }
            ]
        },

        {
            id: 'next-steps',
            section: 'Advanced',
            title: 'Next steps',
            summary:
                'Choose a practical direction after finishing the foundations.',
            tip:
                'Move to DO when you have a concrete goal such as Python, GitHub or SSH.',
            steps: [
                {
                    title: 'Pick a goal',
                    body:
                        'Choose a practical task and apply what you learned instead of continuing to memorize commands.'
                },
                {
                    title: 'Use FIX when blocked',
                    body:
                        'When something fails, search the troubleshooting section before changing multiple settings at once.'
                }
            ]
        }
    ],

    tasks: [
        {
            id: 'python-android',
            title: 'Run Python on Android',
            summary:
                'Set up Python in Termux and run your first script.',
            level:
                'Beginner',
            time:
                '~20 min',
            steps: [
                'Install Python',
                'Verify the installation',
                'Create your first script',
                'Optional: install pip packages',
                'Run the script'
            ],
            results: [
                'Python installed',
                'pip working',
                'A runnable Python script'
            ],
            resources: [
                'Python package reference',
                'Termux package management',
                'Useful Python packages'
            ]
        },

        {
            id: 'install-git',
            title: 'Install Git',
            summary:
                'Install Git, verify it and configure your basic identity.',
            level:
                'Beginner',
            time:
                '~10 min',
            steps: [
                'Update package lists',
                'Install Git',
                'Verify the Git version',
                'Configure your name',
                'Configure your email'
            ],
            results: [
                'Git installed',
                'Identity configured'
            ],
            resources: [
                'Git command reference',
                'GitHub setup'
            ]
        },

        {
            id: 'github',
            title: 'Connect to GitHub',
            summary:
                'Prepare Git and authenticate with GitHub from Termux.',
            level:
                'Intermediate',
            time:
                '~25 min',
            steps: [
                'Install Git',
                'Create or open a repository',
                'Configure authentication',
                'Add a remote',
                'Push your first commit'
            ],
            results: [
                'GitHub remote configured',
                'A successful push'
            ],
            resources: [
                'GitHub documentation',
                'SSH task'
            ]
        },

        {
            id: 'ssh-key',
            title: 'Create SSH key',
            summary:
                'Generate an SSH key pair and prepare it for a remote service.',
            level:
                'Intermediate',
            time:
                '~15 min',
            steps: [
                'Install OpenSSH',
                'Generate a key',
                'Inspect the public key',
                'Add the key to your service',
                'Test the connection'
            ],
            results: [
                'SSH key pair',
                'Working SSH authentication'
            ],
            resources: [
                'SSH reference',
                'GitHub SSH setup'
            ]
        },

        {
            id: 'local-server',
            title: 'Host a website locally',
            summary:
                'Serve a local folder from your Android device for development testing.',
            level:
                'Intermediate',
            time:
                '~15 min',
            steps: [
                'Choose a project folder',
                'Install a runtime',
                'Start a local server',
                'Open the local address',
                'Stop the server safely'
            ],
            results: [
                'Local web server',
                'Browser preview'
            ],
            resources: [
                'Python HTTP server',
                'Node.js package'
            ]
        },

        {
            id: 'backup',
            title: 'Backup your data',
            summary:
                'Prepare a safe copy of important Termux files and configuration.',
            level:
                'Intermediate',
            time:
                '~15 min',
            steps: [
                'Identify important files',
                'Create a backup folder',
                'Copy project files',
                'Export configuration',
                'Verify the backup'
            ],
            results: [
                'Backup copy',
                'Verified important files'
            ],
            resources: [
                'Storage reference',
                'File commands'
            ]
        },

        {
            id: 'cron',
            title: 'Set up a scheduled job',
            summary:
                'Learn the concept of running a repeated command on a schedule.',
            level:
                'Advanced',
            time:
                '~25 min',
            steps: [
                'Choose a repeated task',
                'Prepare the command',
                'Install the required scheduler',
                'Create a schedule',
                'Test and inspect the result'
            ],
            results: [
                'Repeatable command',
                'Working schedule'
            ],
            resources: [
                'Shell scripting',
                'Process reference'
            ]
        },

        {
            id: 'tmux',
            title: 'Use tmux session',
            summary:
                'Keep terminal work organized inside persistent terminal sessions.',
            level:
                'Intermediate',
            time:
                '~20 min',
            steps: [
                'Install tmux',
                'Start a session',
                'Create another window',
                'Detach',
                'Reattach'
            ],
            results: [
                'Persistent terminal session',
                'Multiple terminal windows'
            ],
            resources: [
                'Keyboard shortcuts',
                'Process management'
            ]
        }
    ],

    fixes: [
        {
            id: 'permission-denied',
            title: 'Permission denied',
            tags: [
                'Termux',
                'Storage',
                'Permissions'
            ],
            problem:
                'You get “Permission denied” when trying to access a file, folder or command.',
            cause:
                'The path may be protected, Android storage permission may be missing, or the file permissions do not allow the requested action.',
            steps: [
                {
                    title: 'Check the path and owner',
                    description:
                        'Inspect the target before changing permissions.',
                    code:
                        'ls -l /path'
                },
                {
                    title: 'Enable shared storage when needed',
                    description:
                        'If the target is Android shared storage, request Termux storage access.',
                    code:
                        'termux-setup-storage'
                },
                {
                    title: 'Change permissions only when appropriate',
                    description:
                        'For a file you own, add the permission required by your task.',
                    code:
                        'chmod 755 /path'
                },
                {
                    title: 'Try the command again',
                    description:
                        'Repeat only the command that failed and read the new error if one appears.'
                }
            ],
            related: [
                'Storage access issue',
                'Command not found',
                'Understanding permissions'
            ]
        },

        {
            id: 'repository-errors',
            title: 'Repository errors',
            tags: [
                'Packages',
                'Repository'
            ],
            problem:
                'Package updates fail because a repository cannot be reached or metadata is outdated.',
            cause:
                'The selected mirror may be unavailable, connectivity may be blocked, or local package metadata may be stale.',
            steps: [
                {
                    title: 'Check connectivity',
                    description:
                        'Verify that the device has a working internet connection.'
                },
                {
                    title: 'Refresh package information',
                    description:
                        'Try updating package lists again.',
                    code:
                        'pkg update'
                },
                {
                    title: 'Change repository mirror',
                    description:
                        'Use the Termux repository selector when the current mirror is consistently unavailable.',
                    code:
                        'termux-change-repo'
                }
            ],
            related: [
                'Package not found',
                'Slow performance'
            ]
        },

        {
            id: 'package-not-found',
            title: 'Package not found',
            tags: [
                'Packages'
            ],
            problem:
                'pkg cannot find the package name you entered.',
            cause:
                'The package name may be wrong, package lists may be outdated, or the package may not exist in enabled repositories.',
            steps: [
                {
                    title: 'Update package lists',
                    description:
                        'Refresh package metadata first.',
                    code:
                        'pkg update'
                },
                {
                    title: 'Search the package',
                    description:
                        'Search by a keyword instead of guessing the full name.',
                    code:
                        'pkg search keyword'
                },
                {
                    title: 'Check enabled repositories',
                    description:
                        'Some tools require an additional Termux repository.'
                }
            ],
            related: [
                'Repository errors',
                'Command not found'
            ]
        },

        {
            id: 'storage-access',
            title: 'Storage access issue',
            tags: [
                'Storage',
                'Android'
            ],
            problem:
                'Termux cannot see files you expect to find in Android shared storage.',
            cause:
                'Shared storage access may not have been granted or the path may be different from Termux private storage.',
            steps: [
                {
                    title: 'Request shared storage access',
                    description:
                        'Create the standard storage links.',
                    code:
                        'termux-setup-storage'
                },
                {
                    title: 'Check the storage links',
                    description:
                        'Inspect the storage directory inside your Termux home.',
                    code:
                        'ls ~/storage'
                }
            ],
            related: [
                'Permission denied',
                'Understanding paths'
            ]
        },

        {
            id: 'command-not-found',
            title: 'Command not found',
            tags: [
                'Commands',
                'Packages'
            ],
            problem:
                'The shell reports that a command does not exist.',
            cause:
                'The package that provides the command may not be installed, the command name may be wrong or PATH may be misconfigured.',
            steps: [
                {
                    title: 'Check the command name',
                    description:
                        'Verify spelling and capitalization.'
                },
                {
                    title: 'Search for a package',
                    description:
                        'Search Termux repositories for the tool.',
                    code:
                        'pkg search command-name'
                },
                {
                    title: 'Inspect PATH',
                    description:
                        'Check where the shell looks for executables.',
                    code:
                        'echo $PATH'
                }
            ],
            related: [
                'Package not found',
                'Environment variables'
            ]
        },

        {
            id: 'app-crash',
            title: 'App crashes',
            tags: [
                'Android',
                'App'
            ],
            problem:
                'Termux closes unexpectedly or becomes unstable.',
            cause:
                'A damaged environment, outdated build, resource pressure or unsupported configuration can cause instability.',
            steps: [
                {
                    title: 'Save important work',
                    description:
                        'Back up projects and configuration before destructive troubleshooting.'
                },
                {
                    title: 'Update packages',
                    description:
                        'Update installed tools when the app itself remains usable.',
                    code:
                        'pkg update && pkg upgrade'
                },
                {
                    title: 'Review recent changes',
                    description:
                        'Undo unusual shell configuration or package changes made shortly before the problem began.'
                }
            ],
            related: [
                'Backup your data',
                'Slow performance'
            ]
        },

        {
            id: 'login-issues',
            title: 'Login issues',
            tags: [
                'GitHub',
                'SSH'
            ],
            problem:
                'A remote service rejects your credentials or authentication method.',
            cause:
                'The service may require a token or SSH key instead of a password.',
            steps: [
                {
                    title: 'Identify the authentication method',
                    description:
                        'Check whether your remote expects HTTPS tokens or SSH keys.'
                },
                {
                    title: 'Test SSH when applicable',
                    description:
                        'Verify your SSH authentication separately.',
                    code:
                        'ssh -T git@github.com'
                }
            ],
            related: [
                'Create SSH key',
                'Connect to GitHub'
            ]
        },

        {
            id: 'slow-performance',
            title: 'Slow performance',
            tags: [
                'Performance'
            ],
            problem:
                'Commands, package operations or scripts feel unusually slow.',
            cause:
                'Network mirrors, device resource limits, background work or heavy commands can affect performance.',
            steps: [
                {
                    title: 'Separate network and local slowness',
                    description:
                        'Check whether only downloads are slow or local commands are also affected.'
                },
                {
                    title: 'Stop unnecessary processes',
                    description:
                        'Inspect running processes before starting heavy work.',
                    code:
                        'ps'
                }
            ],
            related: [
                'Repository errors',
                'Process management'
            ]
        }
    ],

    reference: [
        {
            id: 'commands',
            title: 'Essential Commands',
            items: [
                ['pwd', 'Print working directory', 'pwd'],
                ['ls', 'List directory contents', 'ls -la'],
                ['cd [dir]', 'Change directory', 'cd /sdcard'],
                ['mkdir [name]', 'Create a directory', 'mkdir new_folder'],
                ['rm [file]', 'Remove a file', 'rm file.txt'],
                ['cp [src] [dest]', 'Copy files or folders', 'cp a.txt b.txt'],
                ['mv [src] [dest]', 'Move or rename', 'mv old new'],
                ['cat [file]', 'Print a text file', 'cat README.txt'],
                ['clear', 'Clear terminal display', 'clear']
            ]
        },

        {
            id: 'shortcuts',
            title: 'Keyboard Shortcuts',
            items: [
                ['Tab', 'Autocomplete command or path', 'Tab'],
                ['Ctrl + C', 'Interrupt current command', 'Ctrl + C'],
                ['Ctrl + L', 'Clear terminal screen', 'Ctrl + L'],
                ['Ctrl + D', 'Send end-of-input / exit some shells', 'Ctrl + D']
            ]
        },

        {
            id: 'paths',
            title: 'Important Paths',
            items: [
                ['$HOME', 'Termux home directory', 'echo $HOME'],
                ['~/storage', 'Links to shared Android storage', 'ls ~/storage'],
                ['/sdcard', 'Common shared storage path', 'cd /sdcard']
            ]
        },

        {
            id: 'environment',
            title: 'Environment',
            items: [
                ['$PATH', 'Directories searched for commands', 'echo $PATH'],
                ['$HOME', 'Current user home directory', 'echo $HOME'],
                ['$PREFIX', 'Termux installation prefix', 'echo $PREFIX']
            ]
        },

        {
            id: 'packages',
            title: 'Package Management',
            items: [
                ['pkg update', 'Refresh package metadata', 'pkg update'],
                ['pkg upgrade', 'Upgrade installed packages', 'pkg upgrade'],
                ['pkg search [name]', 'Search packages', 'pkg search git'],
                ['pkg install [name]', 'Install a package', 'pkg install git'],
                ['pkg uninstall [name]', 'Remove a package', 'pkg uninstall git']
            ]
        },

        {
            id: 'backup',
            title: 'Backup & Restore',
            items: [
                ['tar', 'Create an archive', 'tar -czf backup.tar.gz folder'],
                ['cp -r', 'Copy a folder recursively', 'cp -r project backup/'],
                ['ls -la', 'Verify copied files', 'ls -la backup/']
            ]
        }
    ]
};


/* =========================================================
   7. Generic Guide Fallback
========================================================= */

function createGenericGuide(application) {
    const app =
        application?.name ||
        'this application';

    return {
        level:
            'Beginner to Advanced',

        lessons: [
            {
                id: 'introduction',
                section: 'Foundations',
                title: `Introduction to ${app}`,
                summary:
                    `Understand what ${app} does, how the guide is organized and where to begin.`,
                tip:
                    'Start with the foundations, then move to practical tasks when you have a specific goal.',
                steps: [
                    {
                        title: `What ${app} is for`,
                        body:
                            application?.longDescription ||
                            application?.description ||
                            `Learn the main purpose of ${app} and the problems it is designed to solve.`,
                        why:
                            'Understanding the purpose first helps you choose the right features instead of changing settings randomly.'
                    },
                    {
                        title: 'How this guide is organized',
                        body:
                            'LEARN teaches the app step by step. DO focuses on outcomes. FIX helps when something fails. REFERENCE gives quick answers.'
                    }
                ]
            },

            {
                id: 'installation',
                section: 'Foundations',
                title: 'Installation & first launch',
                summary:
                    `Prepare ${app} and understand the first-run experience.`,
                tip:
                    'Review permissions carefully and enable only what you need.',
                steps: [
                    {
                        title: 'Install from the trusted source',
                        body:
                            `Use the download source shown by OSGuide for ${app}.`
                    },
                    {
                        title: 'Open the app',
                        body:
                            'Read first-run information and do not rush through permission prompts.'
                    },
                    {
                        title: 'Review essential settings',
                        body:
                            'Before starting, inspect the main settings that affect privacy, storage or connectivity.'
                    }
                ]
            },

            {
                id: 'core-features',
                section: 'Foundations',
                title: 'Core features',
                summary:
                    `Learn the main controls and everyday workflow of ${app}.`,
                tip:
                    'Focus on the features you will actually use before exploring advanced options.',
                steps: [
                    {
                        title: 'Identify the main screen',
                        body:
                            'Understand the main navigation and the location of the most important actions.'
                    },
                    {
                        title: 'Use a core feature',
                        body:
                            `Complete one useful action in ${app} from start to finish.`
                    }
                ]
            },

            {
                id: 'privacy',
                section: 'Advanced',
                title: 'Privacy & permissions',
                summary:
                    `Understand the permissions and privacy-related choices in ${app}.`,
                tip:
                    'Permissions should match the feature you are using.',
                steps: [
                    {
                        title: 'Review permissions',
                        body:
                            'Inspect Android permissions and remove access that is not required for your workflow.'
                    },
                    {
                        title: 'Review app settings',
                        body:
                            'Check privacy, telemetry, network and storage options when the app provides them.'
                    }
                ]
            }
        ],

        tasks: [
            {
                id: 'first-workflow',
                title: `Complete your first ${app} workflow`,
                summary:
                    `Use the main feature of ${app} from start to finish.`,
                level:
                    'Beginner',
                time:
                    '~10 min',
                steps: [
                    'Open the app',
                    'Choose the main feature',
                    'Configure the required options',
                    'Complete the action',
                    'Verify the result'
                ],
                results: [
                    'A completed first workflow',
                    'Understanding of the main controls'
                ],
                resources: [
                    'Getting started lesson',
                    'Privacy & permissions'
                ]
            },

            {
                id: 'configure',
                title: `Configure ${app}`,
                summary:
                    'Review important settings and prepare the app for regular use.',
                level:
                    'Beginner',
                time:
                    '~10 min',
                steps: [
                    'Open settings',
                    'Review privacy',
                    'Review storage',
                    'Review notifications',
                    'Save your choices'
                ],
                results: [
                    'Reviewed configuration',
                    'Safer default setup'
                ],
                resources: [
                    'Privacy lesson',
                    'Settings reference'
                ]
            }
        ],

        fixes: [
            {
                id: 'permission',
                title: 'Permission issue',
                tags: [
                    'Android',
                    'Permissions'
                ],
                problem:
                    `${app} cannot access a feature or file that should be available.`,
                cause:
                    'The required Android permission may be disabled or the selected location may not be available to the app.',
                steps: [
                    {
                        title: 'Identify the affected feature',
                        description:
                            'Confirm exactly which action fails before changing settings.'
                    },
                    {
                        title: 'Review Android permissions',
                        description:
                            `Open Android app settings for ${app} and verify only the permission required by that feature.`
                    },
                    {
                        title: 'Retry the same action',
                        description:
                            'Repeat the original action and check whether the error changed.'
                    }
                ],
                related: [
                    'Storage access',
                    'App settings'
                ]
            },

            {
                id: 'startup',
                title: 'App does not start correctly',
                tags: [
                    'Android',
                    'App'
                ],
                problem:
                    `${app} closes, freezes or cannot reach its normal main screen.`,
                cause:
                    'An outdated build, damaged local state or incompatible configuration can cause startup problems.',
                steps: [
                    {
                        title: 'Check for an update',
                        description:
                            'Verify that you are using a current build from a trusted source.'
                    },
                    {
                        title: 'Review recent changes',
                        description:
                            'Consider whether the problem started immediately after a setting or data change.'
                    }
                ],
                related: [
                    'Update app',
                    'Backup data'
                ]
            }
        ],

        reference: [
            {
                id: 'essentials',
                title: 'Essential Information',
                items: [
                    [
                        'Source',
                        'Resolved application source',
                        application?.source || 'Unknown'
                    ],
                    [
                        'Version',
                        'Current resolved version',
                        application?.version || 'Unknown'
                    ],
                    [
                        'License',
                        'Declared open-source license',
                        application?.license || 'Not specified'
                    ],
                    [
                        'Platform',
                        'Supported platform',
                        application?.platform || 'Android'
                    ]
                ]
            },

            {
                id: 'settings',
                title: 'Settings Checklist',
                items: [
                    [
                        'Permissions',
                        'Review Android permissions',
                        'App info → Permissions'
                    ],
                    [
                        'Notifications',
                        'Review notification access',
                        'App info → Notifications'
                    ],
                    [
                        'Storage',
                        'Review storage behavior',
                        'App settings'
                    ],
                    [
                        'Updates',
                        'Keep the app current',
                        'OSGuide / official source'
                    ]
                ]
            }
        ]
    };
}



/* =========================================================
   7B. Guides Library
   No slug/id = show every published application.
   A slug/id = open that application's existing guide.
========================================================= */

function getGuideApplicationUrl(application) {
    const value =
        String(application?.slug || application?.id || '')
            .trim();

    const key =
        application?.slug
            ? 'slug'
            : 'id';

    const url =
        new URL('guide.html', window.location.href);

    url.searchParams.set(
        key,
        value
    );

    return url.href;
}

function escapeGuideLibraryHtml(value) {
    return String(value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function createGuideLibraryCard(application) {
    const safeName =
        escapeGuideLibraryHtml(application.name);

    const safeDescription =
        escapeGuideLibraryHtml(
            application.description ||
            'Practical guide for this application.'
        );

    const safeCategory =
        escapeGuideLibraryHtml(
            application.category ||
            'Application'
        );

    const safeImageUrl =
        escapeGuideLibraryHtml(
            application.imageUrl || ''
        );

    const guideUrl =
        escapeGuideLibraryHtml(
            getGuideApplicationUrl(application)
        );

    const iconMarkup =
        safeImageUrl
            ? `<img
                    src="${safeImageUrl}"
                    alt="${safeName} logo"
                    loading="lazy"
                    decoding="async"
                    referrerpolicy="no-referrer"
                    style="width:58px;height:58px;border-radius:14px;object-fit:cover;background:#111b26;"
               >`
            : `<div
                    aria-hidden="true"
                    style="
                        width:58px;
                        height:58px;
                        border-radius:14px;
                        display:grid;
                        place-items:center;
                        background:#111b26;
                        border:1px solid #26384c;
                        font-size:22px;
                        font-weight:900;
                    "
               >${escapeGuideLibraryHtml(safeName.charAt(0).toUpperCase())}</div>`;

    return `
        <a
            href="${guideUrl}"
            style="
                display:block;
                padding:18px;
                border:1px solid #26384c;
                border-radius:16px;
                background:#0a131d;
                color:inherit;
                text-decoration:none;
            "
        >
            <div style="display:flex;gap:14px;align-items:center;">
                ${iconMarkup}

                <div style="min-width:0;">
                    <p
                        style="
                            margin:0 0 5px;
                            color:#69a7ff;
                            font-size:11px;
                            font-weight:850;
                            letter-spacing:.05em;
                            text-transform:uppercase;
                        "
                    >${safeCategory}</p>

                    <h2
                        style="
                            margin:0;
                            font-size:18px;
                            line-height:1.25;
                        "
                    >${safeName}</h2>
                </div>
            </div>

            <p
                style="
                    margin:14px 0 0;
                    color:#9fb0c3;
                    line-height:1.65;
                    font-size:14px;
                "
            >${safeDescription}</p>

            <div
                style="
                    margin-top:16px;
                    color:#d9e8f8;
                    font-size:13px;
                    font-weight:800;
                "
            >Open Guide →</div>
        </a>
    `;
}

async function loadGuidesLibrary() {
    const {
        data,
        error
    } =
        await supabase
            .from('applications')
            .select('*')
            .eq('is_published', true)
            .order('added', { ascending: false });

    if (error) {
        throw error;
    }

    return Array.isArray(data)
        ? data.map(normalizeApplication)
        : [];
}

async function renderGuidesLibrary() {
    const applications =
        await loadGuidesLibrary();

    state.application =
        null;

    state.guide =
        null;

    const sidebar =
        document.querySelector('.guide-sidebar');

    if (sidebar) {
        sidebar.hidden =
            true;
    }

    if (guideMain) {
        guideMain.innerHTML = `
            <section
                style="
                    width:min(100%,1120px);
                    margin:0 auto;
                    padding:34px 20px 60px;
                "
            >
                <div style="margin-bottom:28px;">
                    <p
                        style="
                            margin:0 0 8px;
                            color:#69a7ff;
                            font-size:11px;
                            font-weight:900;
                            letter-spacing:.08em;
                        "
                    >OSGUIDE GUIDES</p>

                    <h1
                        style="
                            margin:0;
                            font-size:clamp(30px,6vw,48px);
                            line-height:1.08;
                        "
                    >Learn every published app.</h1>

                    <p
                        style="
                            margin:14px 0 0;
                            max-width:720px;
                            color:#9fb0c3;
                            line-height:1.7;
                        "
                    >
                        ${applications.length} ${applications.length === 1 ? 'application' : 'applications'}
                        available from the same OSGuide catalog.
                        New published applications appear here automatically.
                    </p>
                </div>

                ${
                    applications.length
                        ? `<div
                                style="
                                    display:grid;
                                    grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));
                                    gap:14px;
                                "
                           >
                                ${applications
                                    .map(createGuideLibraryCard)
                                    .join('')}
                           </div>`
                        : `<div
                                style="
                                    padding:24px;
                                    border:1px solid #26384c;
                                    border-radius:16px;
                                    background:#0a131d;
                                    color:#9fb0c3;
                                "
                           >No published applications are available yet.</div>`
                }
            </section>
        `;
    }

    showAppShell();
}

/* =========================================================
   8. Application Loading
========================================================= */

function normalizeApplication(row) {
    return {
        id:
            String(row?.id || ''),

        slug:
            String(row?.slug || '')
                .trim()
                .toLowerCase(),

        name:
            row?.name ||
            'Application',

        description:
            row?.description ||
            '',

        longDescription:
            row?.long_description ||
            row?.description ||
            '',

        version:
            row?.version ||
            'Unknown',

        size:
            row?.size ||
            '',

        source:
            row?.source ||
            'F-Droid',

        license:
            row?.license ||
            '',

        platform:
            row?.platform ||
            'Android',

        category:
            row?.category ||
            'Application',

        downloadUrl:
            row?.download_url ||
            '#',

        imageUrl:
            row?.image_url ||
            ''
    };
}

async function loadApplication() {
    if (!appSlug) {
        throw new Error(
            'No application was selected for this guide.'
        );
    }

    let response =
        await supabase
            .from('applications')
            .select('*')
            .eq('slug', appSlug)
            .eq('is_published', true)
            .limit(1);

    let data =
        response.data;

    let error =
        response.error;

    if (
        (!Array.isArray(data) || data.length === 0) &&
        /^\d+$/.test(appSlug)
    ) {
        response =
            await supabase
                .from('applications')
                .select('*')
                .eq('id', appSlug)
                .eq('is_published', true)
                .limit(1);

        data =
            response.data;

        error =
            response.error;
    }

    if (error) {
        throw error;
    }

    const row =
        Array.isArray(data)
            ? data[0]
            : null;

    if (!row) {
        throw new Error(
            'This application does not exist or is not published.'
        );
    }

    state.application =
        normalizeApplication(row);

    const isTermux =
        state.application.slug === 'termux' ||
        state.application.name.toLowerCase() === 'termux';

    state.guide =
        isTermux
            ? TERMUX_GUIDE
            : createGenericGuide(
                state.application
            );
}


/* =========================================================
   9. Auth
========================================================= */

function getRedirectUrl() {
    return (
        window.location.origin +
        window.location.pathname +
        window.location.search
    );
}

async function startGoogleLogin() {
    if (!googleLoginButton) {
        return;
    }

    googleLoginButton.disabled =
        true;

    if (authStatus) {
        authStatus.textContent =
            'Opening Google sign-in…';
    }

    const {
        error
    } =
        await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo:
                    getRedirectUrl()
            }
        });

    if (error) {
        googleLoginButton.disabled =
            false;

        if (authStatus) {
            authStatus.textContent =
                error.message ||
                'Google sign-in could not be started.';
        }
    }
}

async function signOut() {
    await supabase.auth.signOut();

    state.user =
        null;

    if (accountMenu) {
        accountMenu.hidden =
            true;
    }

    showAuthGate();
}

function showAuthGate() {
    if (authGate) {
        authGate.hidden =
            false;
    }

    if (appShell) {
        appShell.hidden =
            true;
    }
}

function showAppShell() {
    if (authGate) {
        authGate.hidden =
            true;
    }

    if (appShell) {
        appShell.hidden =
            false;
    }
}

function renderUser(user) {
    if (!user) {
        return;
    }

    const metadata =
        user.user_metadata ||
        {};

    const displayName =
        metadata.full_name ||
        metadata.name ||
        user.email ||
        'OSGuide user';

    if (accountName) {
        accountName.textContent =
            displayName;
    }

    if (accountEmail) {
        accountEmail.textContent =
            user.email ||
            '';
    }

    if (accountAvatar) {
        const avatarUrl =
            metadata.avatar_url ||
            metadata.picture ||
            '';

        if (avatarUrl) {
            accountAvatar.innerHTML =
                `<img src="${escapeHTML(avatarUrl)}" alt="">`;
        } else {
            accountAvatar.textContent =
                String(displayName)
                    .trim()
                    .charAt(0)
                    .toUpperCase();
        }
    }
}


/* =========================================================
   10. Progress
========================================================= */

function getProgressStorageKey() {
    const userId =
        state.user?.id ||
        'anonymous';

    const appId =
        state.application?.slug ||
        state.application?.id ||
        appSlug ||
        'app';

    return (
        `osguide-guide-v2-progress-${userId}-${appId}`
    );
}

function loadProgress() {
    try {
        const saved =
            JSON.parse(
                localStorage.getItem(
                    getProgressStorageKey()
                ) ||
                '{}'
            );

        state.progress = {
            completedSteps:
                saved.completedSteps &&
                typeof saved.completedSteps === 'object'
                    ? saved.completedSteps
                    : {},

            completedTasks:
                saved.completedTasks &&
                typeof saved.completedTasks === 'object'
                    ? saved.completedTasks
                    : {},

            feedback:
                saved.feedback &&
                typeof saved.feedback === 'object'
                    ? saved.feedback
                    : {},

            recentlyViewed:
                Array.isArray(
                    saved.recentlyViewed
                )
                    ? saved.recentlyViewed.slice(0, 5)
                    : []
        };
    } catch {
        state.progress = {
            completedSteps: {},
            completedTasks: {},
            feedback: {},
            recentlyViewed: []
        };
    }
}

function saveProgress() {
    try {
        localStorage.setItem(
            getProgressStorageKey(),
            JSON.stringify(
                state.progress
            )
        );
    } catch {
        console.warn(
            'OSGuide could not save guide progress on this device.'
        );
    }
}

function getLessonCompletedSteps(lesson) {
    const completed =
        state.progress.completedSteps[
            lesson.id
        ];

    return Array.isArray(completed)
        ? completed
        : [];
}

function isLessonComplete(lesson) {
    const completed =
        getLessonCompletedSteps(
            lesson
        );

    return (
        lesson.steps.length > 0 &&
        completed.length >=
            lesson.steps.length
    );
}

function getCompletedLessonsCount() {
    return state.guide.lessons.filter(
        isLessonComplete
    ).length;
}

function getOverallLessonProgress() {
    const lessons =
        state.guide?.lessons ||
        [];

    if (!lessons.length) {
        return 0;
    }

    let completedUnits = 0;
    let totalUnits = 0;

    lessons.forEach(
        lesson => {
            completedUnits +=
                Math.min(
                    getLessonCompletedSteps(
                        lesson
                    ).length,
                    lesson.steps.length
                );

            totalUnits +=
                lesson.steps.length;
        }
    );

    if (!totalUnits) {
        return 0;
    }

    return Math.round(
        completedUnits /
        totalUnits *
        100
    );
}

function getLessonProgress(lesson) {
    if (
        !lesson ||
        !lesson.steps.length
    ) {
        return 0;
    }

    return Math.round(
        Math.min(
            getLessonCompletedSteps(
                lesson
            ).length,
            lesson.steps.length
        ) /
        lesson.steps.length *
        100
    );
}

function getFirstIncompleteLessonIndex() {
    const index =
        state.guide.lessons.findIndex(
            lesson =>
                !isLessonComplete(
                    lesson
                )
        );

    return index === -1
        ? 0
        : index;
}

function addRecent(
    type,
    id,
    title
) {
    state.progress.recentlyViewed =
        [
            {
                type,
                id,
                title
            },

            ...state.progress.recentlyViewed.filter(
                item =>
                    !(
                        item.type === type &&
                        item.id === id
                    )
            )
        ]
            .slice(0, 5);

    saveProgress();
    renderRecent();
}


/* =========================================================
   11. Application Header
========================================================= */

function renderApplicationHeader() {
    const application =
        state.application;

    document.title =
        `${application.name} Guide | OSGuide`;

    if (appName) {
        appName.textContent =
            application.name;
    }

    if (appDescription) {
        appDescription.textContent =
            application.description ||
            application.longDescription ||
            `Practical guide for ${application.name}.`;
    }

    if (levelBadge) {
        levelBadge.textContent =
            state.guide.level;
    }

    if (sidebarSource) {
        sidebarSource.textContent =
            `Source: ${application.source}`;
    }

    const iconUrl =
        application.imageUrl ||
        createFallbackIcon(
            application.name
        );

    if (appIcon) {
        appIcon.src =
            iconUrl;

        appIcon.alt =
            `${application.name} logo`;

        appIcon.onerror = () => {
            appIcon.onerror =
                null;

            appIcon.src =
                createFallbackIcon(
                    application.name
                );
        };
    }

    const lessonTotal =
        state.guide.lessons.length;

    const taskTotal =
        state.guide.tasks.length;

    const fixTotal =
        state.guide.fixes.length;

    [
        lessonsCount,
        modeLessonsCount
    ].forEach(
        element => {
            if (element) {
                element.textContent =
                    String(
                        lessonTotal
                    );
            }
        }
    );

    [
        tasksCount,
        modeTasksCount
    ].forEach(
        element => {
            if (element) {
                element.textContent =
                    String(
                        taskTotal
                    );
            }
        }
    );

    [
        fixesCount,
        modeFixesCount
    ].forEach(
        element => {
            if (element) {
                element.textContent =
                    String(
                        fixTotal
                    );
            }
        }
    );
}


/* =========================================================
   12. Home Progress
========================================================= */

function renderHomeProgress() {
    const percentage =
        getOverallLessonProgress();

    const completedLessons =
        getCompletedLessonsCount();

    const totalLessons =
        state.guide.lessons.length;

    const firstIncompleteIndex =
        getFirstIncompleteLessonIndex();

    const activeIndex =
        clamp(
            state.lessonIndex ??
            firstIncompleteIndex,
            0,
            Math.max(
                totalLessons - 1,
                0
            )
        );

    const resumeLesson =
        state.guide.lessons[
            activeIndex
        ] ||
        state.guide.lessons[0];

    if (progressRing) {
        progressRing.style.setProperty(
            '--guide-progress-value',
            `${percentage * 3.6}deg`
        );
    }

    if (progressPercent) {
        progressPercent.textContent =
            `${percentage}%`;
    }

    if (progressTitle) {
        progressTitle.textContent =
            percentage >= 100
                ? 'Learning path complete'
                : percentage > 0
                    ? 'Keep going!'
                    : 'Start learning';
    }

    if (progressSubtitle) {
        progressSubtitle.textContent =
            `${completedLessons} of ${totalLessons} lessons completed`;
    }

    if (!resumeLesson) {
        return;
    }

    const lessonIndex =
        state.guide.lessons.indexOf(
            resumeLesson
        );

    const lessonProgress =
        getLessonProgress(
            resumeLesson
        );

    if (resumeNumber) {
        resumeNumber.textContent =
            `${String(lessonIndex + 1).padStart(2, '0')}.`;
    }

    if (resumeTitle) {
        resumeTitle.textContent =
            resumeLesson.title;
    }

    if (resumeSection) {
        resumeSection.textContent =
            `Learn › ${resumeLesson.section}`;
    }

    if (resumeProgressBar) {
        resumeProgressBar.style.width =
            `${lessonProgress}%`;
    }

    if (resumePercent) {
        resumePercent.textContent =
            `${lessonProgress}%`;
    }
}


/* =========================================================
   13. Recently Viewed
========================================================= */

function renderRecent() {
    if (!recentList) {
        return;
    }

    const items =
        state.progress.recentlyViewed;

    if (!items.length) {
        recentList.innerHTML = `
            <p
                style="
                    color:#617287;
                    font-size:9px;
                    margin-top:8px;
                "
            >
                Your recently opened guide items will appear here.
            </p>
        `;

        return;
    }

    recentList.innerHTML =
        items
            .slice(0, 3)
            .map(
                item => `
                    <button
                        type="button"
                        class="guide-recent-item"
                        data-recent-type="${escapeHTML(item.type)}"
                        data-recent-id="${escapeHTML(item.id)}"
                    >
                        <span class="guide-recent-type">◉</span>
                        <span>${escapeHTML(item.title)}</span>
                        <span class="guide-recent-arrow">›</span>
                    </button>
                `
            )
            .join('');

    recentList
        .querySelectorAll(
            '[data-recent-type]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        openGuideItem(
                            button.dataset.recentType,
                            button.dataset.recentId
                        );
                    }
                );
            }
        );
}


/* =========================================================
   14. Mode Switching
========================================================= */

const MODE_META = {
    learn: {
        number: '1',
        title: 'LEARN',
        subtitle: 'Step-by-step learning',
        numberClass: 'is-learn'
    },

    do: {
        number: '2',
        title: 'DO',
        subtitle: 'Practical tasks',
        numberClass: 'is-do'
    },

    fix: {
        number: '3',
        title: 'FIX',
        subtitle: 'Troubleshooting',
        numberClass: 'is-fix'
    },

    reference: {
        number: '4',
        title: 'REFERENCE',
        subtitle: 'Quick reference',
        numberClass: 'is-reference'
    }
};

function updateModeNavigationState() {
    document
        .querySelectorAll(
            '[data-mode-jump]'
        )
        .forEach(
            button => {
                button.classList.toggle(
                    'is-active',
                    button.dataset.modeJump ===
                        state.mode
                );
            }
        );
}

function setMode(
    mode,
    options = {}
) {
    if (!MODE_META[mode]) {
        return;
    }

    state.mode =
        mode;

    const meta =
        MODE_META[mode];

    if (workspaceNumber) {
        workspaceNumber.textContent =
            meta.number;

        workspaceNumber.className =
            `guide-workspace-number ${meta.numberClass}`;
    }

    if (workspaceTitle) {
        workspaceTitle.textContent =
            meta.title;
    }

    if (workspaceSubtitle) {
        workspaceSubtitle.textContent =
            meta.subtitle;
    }

    const workspaces = {
        learn:
            learnWorkspace,
        do:
            doWorkspace,
        fix:
            fixWorkspace,
        reference:
            referenceWorkspace
    };

    Object.entries(
        workspaces
    )
        .forEach(
            ([key, element]) => {
                if (element) {
                    element.hidden =
                        key !== mode;
                }
            }
        );

    if (mode === 'learn') {
        renderLearn();
    }

    if (mode === 'do') {
        renderDo();
    }

    if (mode === 'fix') {
        renderFix();
    }

    if (mode === 'reference') {
        renderReference();
    }

    updateModeNavigationState();

    if (
        options.scroll !==
        false
    ) {
        scrollWorkspaceIntoView();
    }
}


/* =========================================================
   15. LEARN
========================================================= */

function renderLessonsNavigation() {
    if (!lessonsNavigation) {
        return;
    }

    lessonsNavigation.innerHTML =
        state.guide.lessons
            .map(
                (
                    lesson,
                    index
                ) => {
                    const active =
                        index ===
                        state.lessonIndex;

                    const complete =
                        isLessonComplete(
                            lesson
                        );

                    return `
                        <button
                            type="button"
                            class="guide-workspace-nav-button${active ? ' is-active' : ''}"
                            data-lesson-index="${index}"
                        >
                            <span class="guide-workspace-nav-index">
                                ${String(index + 1).padStart(2, '0')}.
                            </span>

                            <span>
                                ${escapeHTML(lesson.title)}
                            </span>

                            <span
                                class="guide-workspace-nav-state${complete ? ' is-complete' : ''}"
                            >
                                ${complete ? '✓' : active ? '●' : '›'}
                            </span>
                        </button>
                    `;
                }
            )
            .join('');

    lessonsNavigation
        .querySelectorAll(
            '[data-lesson-index]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        state.lessonIndex =
                            Number(
                                button.dataset.lessonIndex
                            );

                        state.stepIndex =
                            0;

                        renderLearn();

                        const lesson =
                            state.guide.lessons[
                                state.lessonIndex
                            ];

                        addRecent(
                            'learn',
                            lesson.id,
                            lesson.title
                        );
                    }
                );
            }
        );
}

function renderMobileLessonsMenu() {
    if (!mobileLessonsMenu) {
        return;
    }

    mobileLessonsMenu.innerHTML =
        state.guide.lessons
            .map(
                (
                    lesson,
                    index
                ) => `
                    <button
                        type="button"
                        class="${index === state.lessonIndex ? 'is-active' : ''}"
                        data-mobile-lesson-index="${index}"
                    >
                        ${String(index + 1).padStart(2, '0')}.
                        ${escapeHTML(lesson.title)}
                    </button>
                `
            )
            .join('');

    mobileLessonsMenu
        .querySelectorAll(
            '[data-mobile-lesson-index]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        state.lessonIndex =
                            Number(
                                button.dataset.mobileLessonIndex
                            );

                        state.stepIndex =
                            0;

                        mobileLessonsMenu.hidden =
                            true;

                        renderLearn();

                        const lesson =
                            state.guide.lessons[
                                state.lessonIndex
                            ];

                        addRecent(
                            'learn',
                            lesson.id,
                            lesson.title
                        );
                    }
                );
            }
        );
}

function renderLessonOutline(
    lesson
) {
    if (!lessonOutline) {
        return;
    }

    lessonOutline.innerHTML =
        lesson.steps
            .map(
                (
                    step,
                    index
                ) => `
                    <li
                        class="${index === state.stepIndex ? 'is-current' : ''}"
                    >
                        <span>${index + 1}</span>
                        <strong>${escapeHTML(step.title)}</strong>
                    </li>
                `
            )
            .join('');
}

function renderCurrentStep(
    lesson
) {
    if (!lessonContent) {
        return;
    }

    const step =
        lesson.steps[
            state.stepIndex
        ];

    if (!step) {
        lessonContent.innerHTML =
            '';

        return;
    }

    const codeHTML =
        step.code
            ? `
                <div class="guide-code-block">
                    <code>$ ${escapeHTML(step.code)}</code>

                    <button
                        type="button"
                        class="guide-copy-button"
                        data-copy="${escapeHTML(step.code)}"
                    >
                        Copy
                    </button>
                </div>
            `
            : '';

    const outputHTML =
        step.output
            ? `
                <div class="guide-expected-output">
                    <small>Expected output</small>
                    <code>${escapeHTML(step.output)}</code>
                </div>
            `
            : '';

    const whyHTML =
        step.why
            ? `
                <div class="guide-why-box">
                    <strong>Why?</strong>
                    <p>${escapeHTML(step.why)}</p>
                </div>
            `
            : '';

    lessonContent.innerHTML = `
        <section class="guide-step-card">
            <span class="guide-step-label">
                Step ${state.stepIndex + 1}
            </span>

            <h4>${escapeHTML(step.title)}</h4>

            <p>${escapeHTML(step.body || '')}</p>

            ${codeHTML}
            ${outputHTML}
            ${whyHTML}
        </section>
    `;

    lessonContent
        .querySelectorAll(
            '[data-copy]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        copyText(
                            button.dataset.copy ||
                            ''
                        );
                    }
                );
            }
        );
}

function renderLearn() {
    const lessons =
        state.guide.lessons;

    if (!lessons.length) {
        return;
    }

    state.lessonIndex =
        clamp(
            state.lessonIndex,
            0,
            lessons.length - 1
        );

    const lesson =
        lessons[
            state.lessonIndex
        ];

    state.stepIndex =
        clamp(
            state.stepIndex,
            0,
            Math.max(
                lesson.steps.length - 1,
                0
            )
        );

    const totalSteps =
        lesson.steps.length;

    const completed =
        getLessonCompletedSteps(
            lesson
        );

    const currentStepComplete =
        completed.includes(
            state.stepIndex
        );

    const currentProgress =
        totalSteps === 0
            ? 0
            : Math.round(
                (
                    state.stepIndex +
                    1
                ) /
                totalSteps *
                100
            );

    if (lessonKicker) {
        lessonKicker.textContent =
            lesson.section.toUpperCase();
    }

    if (lessonTitle) {
        lessonTitle.textContent =
            `${String(state.lessonIndex + 1).padStart(2, '0')}. ${lesson.title}`;
    }

    if (lessonSummary) {
        lessonSummary.textContent =
            lesson.summary;
    }

    if (stepProgressLabel) {
        stepProgressLabel.textContent =
            `Step ${state.stepIndex + 1} of ${totalSteps}`;
    }

    if (stepProgressBar) {
        stepProgressBar.style.width =
            `${currentProgress}%`;
    }

    if (lessonTip) {
        lessonTip.textContent =
            lesson.tip ||
            'Complete each step carefully before moving on.';
    }

    if (mobileLessonLabel) {
        mobileLessonLabel.textContent =
            `${String(state.lessonIndex + 1).padStart(2, '0')}. ${lesson.title}`;
    }

    if (lessonPrevious) {
        lessonPrevious.disabled =
            state.lessonIndex === 0 &&
            state.stepIndex === 0;

        lessonPrevious.style.opacity =
            lessonPrevious.disabled
                ? '0.45'
                : '1';
    }

    if (lessonNext) {
        const atFinalLesson =
            state.lessonIndex ===
            lessons.length - 1;

        const atFinalStep =
            state.stepIndex ===
            totalSteps - 1;

        lessonNext.textContent =
            atFinalLesson &&
            atFinalStep
                ? 'Finish →'
                : 'Next →';
    }

    if (markStepDone) {
        markStepDone.classList.toggle(
            'is-complete',
            currentStepComplete
        );

        markStepDone.textContent =
            currentStepComplete
                ? 'Completed ✓'
                : 'Mark as done ✓';
    }

    renderLessonsNavigation();
    renderMobileLessonsMenu();
    renderLessonOutline(
        lesson
    );
    renderCurrentStep(
        lesson
    );
    renderHomeProgress();
}

function previousLessonStep() {
    const lessons =
        state.guide.lessons;

    if (
        state.stepIndex >
        0
    ) {
        state.stepIndex -= 1;
        renderLearn();
        return;
    }

    if (
        state.lessonIndex >
        0
    ) {
        state.lessonIndex -= 1;

        const previousLesson =
            lessons[
                state.lessonIndex
            ];

        state.stepIndex =
            Math.max(
                previousLesson.steps.length -
                1,
                0
            );

        renderLearn();

        addRecent(
            'learn',
            previousLesson.id,
            previousLesson.title
        );
    }
}

function nextLessonStep() {
    const lessons =
        state.guide.lessons;

    const lesson =
        lessons[
            state.lessonIndex
        ];

    if (
        state.stepIndex <
        lesson.steps.length - 1
    ) {
        state.stepIndex += 1;
        renderLearn();
        return;
    }

    if (
        state.lessonIndex <
        lessons.length - 1
    ) {
        state.lessonIndex += 1;
        state.stepIndex = 0;

        const nextLesson =
            lessons[
                state.lessonIndex
            ];

        renderLearn();

        addRecent(
            'learn',
            nextLesson.id,
            nextLesson.title
        );

        return;
    }

    showToast(
        'You reached the end of this learning path.'
    );
}

function toggleCurrentStepComplete() {
    const lesson =
        state.guide.lessons[
            state.lessonIndex
        ];

    const completed =
        new Set(
            getLessonCompletedSteps(
                lesson
            )
        );

    if (
        completed.has(
            state.stepIndex
        )
    ) {
        completed.delete(
            state.stepIndex
        );
    } else {
        completed.add(
            state.stepIndex
        );
    }

    state.progress.completedSteps[
        lesson.id
    ] =
        Array.from(
            completed
        )
            .sort(
                (a, b) =>
                    a - b
            );

    saveProgress();
    renderLearn();

    if (
        isLessonComplete(
            lesson
        )
    ) {
        showToast(
            `${lesson.title} completed.`
        );
    }
}


/* =========================================================
   16. DO
========================================================= */

function renderTasksNavigation() {
    if (!tasksNavigation) {
        return;
    }

    tasksNavigation.innerHTML =
        state.guide.tasks
            .map(
                (
                    task,
                    index
                ) => {
                    const active =
                        index ===
                        state.taskIndex;

                    const completed =
                        Boolean(
                            state.progress.completedTasks[
                                task.id
                            ]
                        );

                    return `
                        <button
                            type="button"
                            class="guide-workspace-nav-button${active ? ' is-active' : ''}"
                            data-task-index="${index}"
                        >
                            <span class="guide-workspace-nav-index">
                                ${String(index + 1).padStart(2, '0')}.
                            </span>

                            <span>${escapeHTML(task.title)}</span>

                            <span
                                class="guide-workspace-nav-state${completed ? ' is-complete' : ''}"
                            >
                                ${completed ? '✓' : active ? '●' : '›'}
                            </span>
                        </button>
                    `;
                }
            )
            .join('');

    tasksNavigation
        .querySelectorAll(
            '[data-task-index]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        state.taskIndex =
                            Number(
                                button.dataset.taskIndex
                            );

                        renderDo();

                        const task =
                            state.guide.tasks[
                                state.taskIndex
                            ];

                        addRecent(
                            'do',
                            task.id,
                            task.title
                        );
                    }
                );
            }
        );
}

function renderDo() {
    const tasks =
        state.guide.tasks;

    if (!tasks.length) {
        return;
    }

    state.taskIndex =
        clamp(
            state.taskIndex,
            0,
            tasks.length - 1
        );

    const task =
        tasks[
            state.taskIndex
        ];

    if (taskTitle) {
        taskTitle.textContent =
            task.title;
    }

    if (taskSummary) {
        taskSummary.textContent =
            task.summary;
    }

    if (taskLevel) {
        taskLevel.textContent =
            task.level;
    }

    if (taskTime) {
        taskTime.textContent =
            task.time;
    }

    if (taskSteps) {
        taskSteps.innerHTML =
            task.steps
                .map(
                    (
                        step,
                        index
                    ) => `
                        <button
                            type="button"
                            class="guide-checklist-item"
                            data-task-step="${index}"
                        >
                            <span class="guide-checklist-index">
                                ${index + 1}
                            </span>

                            <span>${escapeHTML(step)}</span>

                            <span class="guide-checklist-state">
                                ○
                            </span>
                        </button>
                    `
                )
                .join('');

        taskSteps
            .querySelectorAll(
                '[data-task-step]'
            )
            .forEach(
                button => {
                    button.addEventListener(
                        'click',
                        () => {
                            button.classList.toggle(
                                'is-complete'
                            );

                            const stateElement =
                                button.querySelector(
                                    '.guide-checklist-state'
                                );

                            if (stateElement) {
                                stateElement.textContent =
                                    button.classList.contains(
                                        'is-complete'
                                    )
                                        ? '✓'
                                        : '○';
                            }
                        }
                    );
                }
            );
    }

    if (taskResults) {
        taskResults.innerHTML =
            task.results
                .map(
                    result =>
                        `<li>${escapeHTML(result)}</li>`
                )
                .join('');
    }

    if (taskResources) {
        taskResources.innerHTML =
            task.resources
                .map(
                    resource => `
                        <button
                            type="button"
                            class="guide-resource-link"
                        >
                            ${escapeHTML(resource)} →
                        </button>
                    `
                )
                .join('');
    }

    if (taskStartButton) {
        const completed =
            Boolean(
                state.progress.completedTasks[
                    task.id
                ]
            );

        taskStartButton.textContent =
            completed
                ? 'Task completed ✓'
                : 'Mark Task Complete';

        taskStartButton.classList.toggle(
            'is-complete',
            completed
        );
    }

    renderTasksNavigation();
}

function toggleTaskComplete() {
    const task =
        state.guide.tasks[
            state.taskIndex
        ];

    if (!task) {
        return;
    }

    state.progress.completedTasks[
        task.id
    ] =
        !state.progress.completedTasks[
            task.id
        ];

    saveProgress();
    renderDo();

    showToast(
        state.progress.completedTasks[
            task.id
        ]
            ? `${task.title} completed.`
            : `${task.title} marked incomplete.`
    );
}


/* =========================================================
   17. FIX
========================================================= */

function renderFixesNavigation() {
    if (!fixesNavigation) {
        return;
    }

    fixesNavigation.innerHTML =
        state.guide.fixes
            .map(
                (
                    fix,
                    index
                ) => `
                    <button
                        type="button"
                        class="guide-workspace-nav-button${index === state.fixIndex ? ' is-active' : ''}"
                        data-fix-index="${index}"
                    >
                        <span class="guide-workspace-nav-index">
                            ${String(index + 1).padStart(2, '0')}.
                        </span>

                        <span>${escapeHTML(fix.title)}</span>

                        <span class="guide-workspace-nav-state">
                            ${index === state.fixIndex ? '●' : '›'}
                        </span>
                    </button>
                `
            )
            .join('');

    fixesNavigation
        .querySelectorAll(
            '[data-fix-index]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        state.fixIndex =
                            Number(
                                button.dataset.fixIndex
                            );

                        renderFix();

                        const fix =
                            state.guide.fixes[
                                state.fixIndex
                            ];

                        addRecent(
                            'fix',
                            fix.id,
                            fix.title
                        );
                    }
                );
            }
        );
}

function renderFix() {
    const fixes =
        state.guide.fixes;

    if (!fixes.length) {
        return;
    }

    state.fixIndex =
        clamp(
            state.fixIndex,
            0,
            fixes.length - 1
        );

    const fix =
        fixes[
            state.fixIndex
        ];

    if (fixTitle) {
        fixTitle.textContent =
            fix.title;
    }

    if (fixTags) {
        fixTags.innerHTML =
            fix.tags
                .map(
                    tag =>
                        `<span>${escapeHTML(tag)}</span>`
                )
                .join('');
    }

    if (fixProblem) {
        fixProblem.textContent =
            fix.problem;
    }

    if (fixCause) {
        fixCause.textContent =
            fix.cause;
    }

    if (fixSteps) {
        fixSteps.innerHTML =
            fix.steps
                .map(
                    (
                        step,
                        index
                    ) => `
                        <article class="guide-solution-step">
                            <span class="guide-solution-step-index">
                                ${index + 1}
                            </span>

                            <div class="guide-solution-step-copy">
                                <strong>${escapeHTML(step.title)}</strong>

                                <p>${escapeHTML(step.description || '')}</p>

                                ${
                                    step.code
                                        ? `
                                            <div class="guide-code-block">
                                                <code>$ ${escapeHTML(step.code)}</code>

                                                <button
                                                    type="button"
                                                    class="guide-copy-button"
                                                    data-copy="${escapeHTML(step.code)}"
                                                >
                                                    Copy
                                                </button>
                                            </div>
                                        `
                                        : ''
                                }
                            </div>
                        </article>
                    `
                )
                .join('');

        fixSteps
            .querySelectorAll(
                '[data-copy]'
            )
            .forEach(
                button => {
                    button.addEventListener(
                        'click',
                        () => {
                            copyText(
                                button.dataset.copy ||
                                ''
                            );
                        }
                    );
                }
            );
    }

    if (fixRelated) {
        fixRelated.innerHTML =
            fix.related
                .map(
                    related => `
                        <button
                            type="button"
                            class="guide-related-link"
                        >
                            ${escapeHTML(related)} →
                        </button>
                    `
                )
                .join('');
    }

    document
        .querySelectorAll(
            '.guide-feedback-button'
        )
        .forEach(
            button => {
                const selected =
                    state.progress.feedback[
                        fix.id
                    ] ===
                    button.dataset.feedback;

                button.classList.toggle(
                    'is-selected',
                    selected
                );
            }
        );

    renderFixesNavigation();
}


/* =========================================================
   18. REFERENCE
========================================================= */

function renderReferenceNavigation() {
    if (!referenceNavigation) {
        return;
    }

    referenceNavigation.innerHTML =
        state.guide.reference
            .map(
                (
                    section,
                    index
                ) => `
                    <button
                        type="button"
                        class="guide-workspace-nav-button${index === state.referenceIndex ? ' is-active' : ''}"
                        data-reference-index="${index}"
                    >
                        <span class="guide-workspace-nav-index">
                            ${String(index + 1).padStart(2, '0')}.
                        </span>

                        <span>${escapeHTML(section.title)}</span>

                        <span class="guide-workspace-nav-state">
                            ${index === state.referenceIndex ? '●' : '›'}
                        </span>
                    </button>
                `
            )
            .join('');

    referenceNavigation
        .querySelectorAll(
            '[data-reference-index]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        state.referenceIndex =
                            Number(
                                button.dataset.referenceIndex
                            );

                        renderReference();

                        const section =
                            state.guide.reference[
                                state.referenceIndex
                            ];

                        addRecent(
                            'reference',
                            section.id,
                            section.title
                        );
                    }
                );
            }
        );
}

function getFilteredReferenceItems(
    section
) {
    const query =
        String(
            referenceSearchInput?.value ||
            ''
        )
            .trim()
            .toLowerCase();

    if (!query) {
        return section.items;
    }

    return section.items.filter(
        item =>
            item
                .join(' ')
                .toLowerCase()
                .includes(query)
    );
}

function renderReference() {
    const sections =
        state.guide.reference;

    if (!sections.length) {
        return;
    }

    state.referenceIndex =
        clamp(
            state.referenceIndex,
            0,
            sections.length - 1
        );

    const section =
        sections[
            state.referenceIndex
        ];

    const items =
        getFilteredReferenceItems(
            section
        );

    if (referenceTitle) {
        referenceTitle.textContent =
            section.title;
    }

    if (referenceTableBody) {
        referenceTableBody.innerHTML =
            items
                .map(
                    item => `
                        <tr>
                            <td class="guide-reference-command-cell">
                                ${escapeHTML(item[0])}
                            </td>

                            <td>
                                ${escapeHTML(item[1])}
                            </td>

                            <td>
                                ${escapeHTML(item[2])}
                            </td>
                        </tr>
                    `
                )
                .join('');
    }

    if (referenceMobileList) {
        referenceMobileList.innerHTML =
            items
                .map(
                    item => `
                        <button
                            type="button"
                            class="guide-reference-mobile-item"
                            data-copy="${escapeHTML(item[2])}"
                        >
                            <span>
                                <strong>${escapeHTML(item[0])}</strong>
                                <small>${escapeHTML(item[1])}</small>
                            </span>

                            <span>›</span>
                        </button>
                    `
                )
                .join('');

        referenceMobileList
            .querySelectorAll(
                '[data-copy]'
            )
            .forEach(
                button => {
                    button.addEventListener(
                        'click',
                        () => {
                            copyText(
                                button.dataset.copy ||
                                ''
                            );
                        }
                    );
                }
            );
    }

    renderReferenceNavigation();
}


/* =========================================================
   19. Global Search
========================================================= */

function buildSearchIndex() {
    const index =
        [];

    state.guide.lessons.forEach(
        lesson => {
            index.push({
                type:
                    'learn',
                id:
                    lesson.id,
                title:
                    lesson.title,
                subtitle:
                    lesson.summary
            });

            lesson.steps.forEach(
                step => {
                    index.push({
                        type:
                            'learn',
                        id:
                            lesson.id,
                        title:
                            step.title,
                        subtitle:
                            lesson.title
                    });
                }
            );
        }
    );

    state.guide.tasks.forEach(
        task => {
            index.push({
                type:
                    'do',
                id:
                    task.id,
                title:
                    task.title,
                subtitle:
                    task.summary
            });
        }
    );

    state.guide.fixes.forEach(
        fix => {
            index.push({
                type:
                    'fix',
                id:
                    fix.id,
                title:
                    fix.title,
                subtitle:
                    fix.problem
            });
        }
    );

    state.guide.reference.forEach(
        section => {
            index.push({
                type:
                    'reference',
                id:
                    section.id,
                title:
                    section.title,
                subtitle:
                    'Reference section'
            });

            section.items.forEach(
                item => {
                    index.push({
                        type:
                            'reference',
                        id:
                            section.id,
                        title:
                            item[0],
                        subtitle:
                            item[1]
                    });
                }
            );
        }
    );

    return index;
}

function renderGlobalSearch() {
    if (
        !globalSearchInput ||
        !searchResults
    ) {
        return;
    }

    const query =
        globalSearchInput.value
            .trim()
            .toLowerCase();

    if (!query) {
        searchResults.hidden =
            true;

        searchResults.innerHTML =
            '';

        return;
    }

    const matches =
        buildSearchIndex()
            .filter(
                item =>
                    (
                        item.title +
                        ' ' +
                        item.subtitle
                    )
                        .toLowerCase()
                        .includes(
                            query
                        )
            )
            .slice(
                0,
                8
            );

    if (!matches.length) {
        searchResults.innerHTML = `
            <div
                style="
                    padding:12px;
                    color:#6f8094;
                    font-size:10px;
                "
            >
                No matching guide content.
            </div>
        `;

        searchResults.hidden =
            false;

        return;
    }

    searchResults.innerHTML =
        matches
            .map(
                item => `
                    <button
                        type="button"
                        class="guide-search-result"
                        data-search-type="${escapeHTML(item.type)}"
                        data-search-id="${escapeHTML(item.id)}"
                    >
                        <span class="guide-search-result-type">
                            ${escapeHTML(item.type.toUpperCase())}
                        </span>

                        <span class="guide-search-result-copy">
                            <strong>${escapeHTML(item.title)}</strong>
                            <small>${escapeHTML(item.subtitle)}</small>
                        </span>

                        <span class="guide-search-result-arrow">›</span>
                    </button>
                `
            )
            .join('');

    searchResults.hidden =
        false;

    searchResults
        .querySelectorAll(
            '[data-search-type]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        openGuideItem(
                            button.dataset.searchType,
                            button.dataset.searchId
                        );

                        globalSearchInput.value =
                            '';

                        searchResults.hidden =
                            true;
                    }
                );
            }
        );
}


/* =========================================================
   20. Open Guide Item
========================================================= */

function openGuideItem(
    type,
    id
) {
    if (type === 'learn') {
        const index =
            state.guide.lessons.findIndex(
                item =>
                    item.id === id
            );

        if (index !== -1) {
            state.lessonIndex =
                index;

            state.stepIndex =
                0;

            setMode(
                'learn'
            );
        }

        return;
    }

    if (type === 'do') {
        const index =
            state.guide.tasks.findIndex(
                item =>
                    item.id === id
            );

        if (index !== -1) {
            state.taskIndex =
                index;

            setMode(
                'do'
            );
        }

        return;
    }

    if (type === 'fix') {
        const index =
            state.guide.fixes.findIndex(
                item =>
                    item.id === id
            );

        if (index !== -1) {
            state.fixIndex =
                index;

            setMode(
                'fix'
            );
        }

        return;
    }

    if (type === 'reference') {
        const index =
            state.guide.reference.findIndex(
                item =>
                    item.id === id
            );

        if (index !== -1) {
            state.referenceIndex =
                index;

            setMode(
                'reference'
            );
        }
    }
}


/* =========================================================
   21. Mobile Drawer / Account
========================================================= */

function openMobileDrawer() {
    if (mobileDrawerShell) {
        mobileDrawerShell.hidden =
            false;
    }

    if (mobileMenuButton) {
        mobileMenuButton.setAttribute(
            'aria-expanded',
            'true'
        );
    }
}

function closeMobileDrawer() {
    if (mobileDrawerShell) {
        mobileDrawerShell.hidden =
            true;
    }

    if (mobileMenuButton) {
        mobileMenuButton.setAttribute(
            'aria-expanded',
            'false'
        );
    }
}

function toggleAccountMenu() {
    if (!accountMenu) {
        return;
    }

    accountMenu.hidden =
        !accountMenu.hidden;

    if (accountButton) {
        accountButton.setAttribute(
            'aria-expanded',
            String(
                !accountMenu.hidden
            )
        );
    }
}


/* =========================================================
   22. Events
========================================================= */

function attachEvents() {
    googleLoginButton?.addEventListener(
        'click',
        startGoogleLogin
    );

    signOutButton?.addEventListener(
        'click',
        signOut
    );

    accountButton?.addEventListener(
        'click',
        event => {
            event.stopPropagation();
            toggleAccountMenu();
        }
    );

    document.addEventListener(
        'click',
        event => {
            if (
                accountMenu &&
                accountButton &&
                !accountMenu.hidden &&
                !accountMenu.contains(
                    event.target
                ) &&
                !accountButton.contains(
                    event.target
                )
            ) {
                accountMenu.hidden =
                    true;

                accountButton.setAttribute(
                    'aria-expanded',
                    'false'
                );
            }
        }
    );

    document
        .querySelectorAll(
            '[data-guide-mode]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        setMode(
                            button.dataset.guideMode
                        );
                    }
                );
            }
        );

    document
        .querySelectorAll(
            '[data-mode-jump]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        closeMobileDrawer();

                        setMode(
                            button.dataset.modeJump
                        );
                    }
                );
            }
        );

    document
        .querySelectorAll(
            '[data-sidebar-placeholder]'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        showToast(
                            'This area will be connected in a later OSGuide step.'
                        );
                    }
                );
            }
        );

    continueButton?.addEventListener(
        'click',
        () => {
            state.lessonIndex =
                getFirstIncompleteLessonIndex();

            state.stepIndex =
                0;

            setMode(
                'learn'
            );

            const lesson =
                state.guide.lessons[
                    state.lessonIndex
                ];

            addRecent(
                'learn',
                lesson.id,
                lesson.title
            );
        }
    );

    resumeButton?.addEventListener(
        'click',
        () => {
            setMode(
                'learn'
            );
        }
    );

    lessonPrevious?.addEventListener(
        'click',
        previousLessonStep
    );

    lessonNext?.addEventListener(
        'click',
        nextLessonStep
    );

    markStepDone?.addEventListener(
        'click',
        toggleCurrentStepComplete
    );

    taskStartButton?.addEventListener(
        'click',
        toggleTaskComplete
    );

    document
        .querySelectorAll(
            '.guide-feedback-button'
        )
        .forEach(
            button => {
                button.addEventListener(
                    'click',
                    () => {
                        const fix =
                            state.guide.fixes[
                                state.fixIndex
                            ];

                        if (!fix) {
                            return;
                        }

                        state.progress.feedback[
                            fix.id
                        ] =
                            button.dataset.feedback;

                        saveProgress();
                        renderFix();

                        showToast(
                            'Thanks for the feedback.'
                        );
                    }
                );
            }
        );

    referenceSearchInput?.addEventListener(
        'input',
        renderReference
    );

    globalSearchInput?.addEventListener(
        'input',
        renderGlobalSearch
    );

    document.addEventListener(
        'keydown',
        event => {
            if (
                event.key === '/' &&
                document.activeElement?.tagName !==
                    'INPUT'
            ) {
                event.preventDefault();

                globalSearchInput?.focus();
            }

            if (
                event.key ===
                'Escape'
            ) {
                if (searchResults) {
                    searchResults.hidden =
                        true;
                }

                if (accountMenu) {
                    accountMenu.hidden =
                        true;
                }

                if (mobileLessonsMenu) {
                    mobileLessonsMenu.hidden =
                        true;
                }

                closeMobileDrawer();
            }
        }
    );

    mobileLessonsButton?.addEventListener(
        'click',
        () => {
            if (mobileLessonsMenu) {
                mobileLessonsMenu.hidden =
                    !mobileLessonsMenu.hidden;
            }
        }
    );

    mobileMenuButton?.addEventListener(
        'click',
        openMobileDrawer
    );

    mobileDrawerBackdrop?.addEventListener(
        'click',
        closeMobileDrawer
    );

    mobileDrawerClose?.addEventListener(
        'click',
        closeMobileDrawer
    );

    workspaceTopButton?.addEventListener(
        'click',
        () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        }
    );
}


/* =========================================================
   23. Render All
========================================================= */

function renderAll() {
    renderApplicationHeader();
    renderHomeProgress();
    renderRecent();

    renderLearn();
    renderDo();
    renderFix();
    renderReference();

    setMode(
        state.mode,
        {
            scroll:
                false
        }
    );
}


/* =========================================================
   24. Fatal Error
========================================================= */

function showFatalError(
    message
) {
    showAppShell();

    if (!guideMain) {
        return;
    }

    guideMain.innerHTML = `
        <section
            style="
                width:min(100%,760px);
                margin:90px auto 0;
                padding:28px;
                border:1px solid #26384c;
                border-radius:14px;
                background:#0a131d;
            "
        >
            <p
                style="
                    color:#ff7c86;
                    font-size:11px;
                    font-weight:850;
                "
            >
                GUIDE UNAVAILABLE
            </p>

            <h1
                style="
                    margin-top:8px;
                    font-size:30px;
                "
            >
                The guide could not be loaded.
            </h1>

            <p
                style="
                    margin-top:10px;
                    color:#8b9bae;
                    font-size:13px;
                    line-height:1.65;
                "
            >
                ${escapeHTML(message)}
            </p>

            <a
                href="index.html"
                style="
                    display:inline-flex;
                    min-height:40px;
                    align-items:center;
                    margin-top:18px;
                    padding:0 13px;
                    border-radius:8px;
                    background:#1f65dd;
                    color:#fff;
                    font-size:11px;
                    font-weight:800;
                "
            >
                Return to OSGuide
            </a>
        </section>
    `;
}


/* =========================================================
   25. Authenticated Initialization
========================================================= */

async function initializeAuthenticatedGuide(
    user
) {
    state.user =
        user;

    renderUser(
        user
    );

    try {
        if (!appSlug) {
            await renderGuidesLibrary();
            return;
        }

        await loadApplication();

        loadProgress();

        state.lessonIndex =
            getFirstIncompleteLessonIndex();

        state.stepIndex =
            0;

        renderAll();

        showAppShell();

        const lesson =
            state.guide.lessons[
                state.lessonIndex
            ] ||
            state.guide.lessons[0];

        if (lesson) {
            addRecent(
                'learn',
                lesson.id,
                lesson.title
            );
        }
    } catch (error) {
        console.error(
            'OSGuide Guide initialization error:',
            error
        );

        showFatalError(
            error?.message ||
            'Unknown guide loading error.'
        );
    }
}


/* =========================================================
   26. Startup
========================================================= */

async function initialize() {
    attachEvents();

    const {
        data,
        error
    } =
        await supabase.auth.getSession();

    if (error) {
        console.error(
            'OSGuide auth session error:',
            error
        );
    }

    const user =
        data?.session?.user ||
        null;

    if (!user) {
        showAuthGate();
    } else {
        await initializeAuthenticatedGuide(
            user
        );
    }

    supabase.auth.onAuthStateChange(
        async (
            event,
            session
        ) => {
            if (
                event === 'SIGNED_OUT' ||
                !session?.user
            ) {
                showAuthGate();
                return;
            }

            if (
                event === 'SIGNED_IN' ||
                event === 'TOKEN_REFRESHED'
            ) {
                state.user =
                    session.user;

                renderUser(
                    session.user
                );

                if (!state.application || !appSlug) {
                    await initializeAuthenticatedGuide(
                        session.user
                    );
                } else {
                    showAppShell();
                }
            }
        }
    );
}

initialize();
