'use strict';

const SUPABASE_URL =
    'https://rqvicenfdzlleureteis.supabase.co';

const SUPABASE_PUBLISHABLE_KEY =
    'sb_publishable_U64um_oKyNG0zXHQu6PuTg_lR9rSIwA';

const supabaseClient = window.supabase.createClient(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY
);

const loginForm =
    document.getElementById('login-form');

const emailInput =
    document.getElementById('email');

const passwordInput =
    document.getElementById('password');

loginForm.addEventListener(
    'submit',
    async event => {
        event.preventDefault();

        const email =
            emailInput.value.trim();

        const password =
            passwordInput.value;

        if (!email || !password) {
            alert(
                'Please enter your email and password.'
            );
            return;
        }

        const { error } =
            await supabaseClient.auth
                .signInWithPassword({
                    email,
                    password
                });

        if (error) {
            console.error(
                'Admin login failed:',
                error
            );

            alert(
                'Login failed. Check your email and password.'
            );

            return;
        }

        alert(
            'Login successful.'
        );
    }
);
