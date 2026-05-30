
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('waitlist-form');
    const emailInput = document.getElementById('email-input');
    const ctaButton = form.querySelector('.cta-button');
    const successMessage = document.getElementById('success-message');

    if (form) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault(); // Evita el envío por defecto del formulario

            const email = emailInput.value.trim();

            if (!email) {
                alert('Por favor, ingresa tu dirección de correo electrónico.');
                return;
            }

            // Validación de formato de email simple
            if (!/\S+@\S+\.\S+/.test(email)) {
                alert('Por favor, ingresa una dirección de correo electrónico válida.');
                return;
            }

            // Cambiar el estado del botón a "Enviando..."
            const originalButtonText = ctaButton.textContent;
            ctaButton.textContent = 'Enviando...';
            ctaButton.disabled = true;
            ctaButton.style.opacity = '0.7';

            try {
                // Simulación de envío a un endpoint /submit
                const response = await fetch('/submit', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ email: email }),
                });

                if (response.ok) {
                    // Si el envío fue exitoso, muestra el mensaje de éxito
                    form.style.display = 'none'; // Oculta el formulario
                    successMessage.style.display = 'block'; // Muestra el mensaje de éxito
                } else {
                    // Manejo de errores si la respuesta no es OK
                    const errorData = await response.json();
                    alert(`Error al registrar tu email: ${errorData.message || 'Inténtalo de nuevo.'}`);
                }
            } catch (error) {
                // Manejo de errores de red o del fetch
                console.error('Error al enviar el formulario:', error);
                alert('Hubo un problema de conexión. Por favor, inténtalo de nuevo más tarde.');
            } finally {
                // Restaura el botón a su estado original después de un tiempo o un error
                ctaButton.textContent = originalButtonText;
                ctaButton.disabled = false;
                ctaButton.style.opacity = '1';
                emailInput.value = ''; // Limpia el campo del email
            }
        });
    }
});
