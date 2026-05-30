
document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('.waitlist-form');

    forms.forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const emailInput = form.querySelector('input[type="email"]');
            const submitButton = form.querySelector('.cta-button');
            const successMessage = form.nextElementSibling; // Asume que el mensaje de éxito es el siguiente hermano

            const email = emailInput.value.trim();

            if (!email) {
                alert('Por favor, introduce tu correo electrónico.');
                return;
            }

            // Validación básica de formato de correo electrónico
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(email)) {
                alert('Por favor, introduce un formato de correo electrónico válido.');
                return;
            }

            // Cambiar estado del botón a "enviando"
            const originalButtonText = submitButton.textContent;
            submitButton.textContent = 'Enviando...';
            submitButton.disabled = true;

            try {
                const response = await fetch('/submit', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ email: email }),
                });

                if (response.ok) {
                    // Ocultar formulario y mostrar mensaje de éxito
                    form.classList.add('hidden');
                    successMessage.classList.remove('hidden');
                    successMessage.classList.add('visible'); // Para la animación de aparición
                    emailInput.value = ''; // Limpiar campo
                } else {
                    const errorData = await response.json();
                    alert('Error al suscribirse: ' + (errorData.message || 'Inténtalo de nuevo.'));
                }
            } catch (error) {
                console.error('Error al enviar el formulario:', error);
                alert('Ocurrió un error inesperado. Por favor, inténtalo más tarde.');
            } finally {
                // Restaurar botón si no fue exitoso o si quieres que vuelva después de un tiempo
                if (form.classList.contains('hidden')) { // Si el formulario ya está oculto, no restaurar el botón
                    // No hacer nada, el formulario ya fue reemplazado por el mensaje de éxito
                } else {
                    submitButton.textContent = originalButtonText;
                    submitButton.disabled = false;
                }
            }
        });
    });
});
