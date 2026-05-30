document.addEventListener('DOMContentLoaded', () => {
    const waitlistForm = document.getElementById('waitlist-form');
    const emailInput = document.getElementById('email-input');
    const submitButton = waitlistForm.querySelector('.waitlist-submit-button');
    const buttonText = submitButton.querySelector('.button-text');
    const formMessage = document.getElementById('form-message');

    // Smooth scroll for navigation links
    document.querySelectorAll('nav a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Handle hero CTA click - scrolls to the VIP access section
    const heroCta = document.getElementById('hero-cta');
    if (heroCta) {
        heroCta.addEventListener('click', () => {
            document.getElementById('vip-access').scrollIntoView({
                behavior: 'smooth'
            });
        });
    }

    waitlistForm.addEventListener('submit', async (e) => {
        e.preventDefault(); // Prevent default form submission

        // Basic client-side validation
        const email = emailInput.value.trim();
        if (!email) {
            displayMessage('Please enter your email address.', 'error');
            return;
        }
        if (!validateEmail(email)) {
            displayMessage('Please enter a valid email address.', 'error');
            return;
        }

        // Show loading state
        submitButton.classList.add('loading');
        buttonText.textContent = ''; // Clear text
        // Note: The spinner is controlled via CSS based on the 'loading' class

        try {
            const response = await fetch('/submit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email: email }),
            });

            if (response.ok) {
                // Assuming the backend returns a success message or just status 200
                displayMessage('Thank you for joining the VIP Pre-Release! We\'ll be in touch with updates.', 'success');
                emailInput.value = ''; // Clear the input
            } else {
                // Handle server errors or non-200 responses
                const errorData = await response.json();
                displayMessage(errorData.message || 'Something went wrong. Please try again.', 'error');
            }
        } catch (error) {
            console.error('Submission error:', error);
            displayMessage('Network error. Please check your connection and try again.', 'error');
        } finally {
            // Hide loading state
            submitButton.classList.remove('loading');
            buttonText.textContent = 'Join VIP Pre-Release'; // Restore original text
        }
    });

    function validateEmail(email) {
        // Regex for basic email validation
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(String(email).toLowerCase());
    }

    function displayMessage(message, type) {
        formMessage.textContent = message;
        formMessage.className = 'form-message show'; // Reset classes
        if (type === 'success') {
            formMessage.classList.add('success-message');
        } else {
            formMessage.classList.add('error-message');
        }

        // Automatically hide message after 5 seconds
        setTimeout(() => {
            formMessage.classList.remove('show');
        }, 5000);
    }
});