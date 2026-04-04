/* ============================================================
   Daniel Okonek — Site Script
   ============================================================ */

// --- Sticky nav ---
const header = document.getElementById('header');
const hero   = document.getElementById('hero');

if (header && hero) {
  new IntersectionObserver(
    ([e]) => header.classList.toggle('scrolled', !e.isIntersecting),
    { threshold: 0.05 }
  ).observe(hero);
}

// --- Scroll reveal ---
const revealEls = document.querySelectorAll('[data-reveal]');
if (revealEls.length) {
  const io = new IntersectionObserver(
    (entries) => entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('is-visible');
        io.unobserve(e.target);
      }
    }),
    { threshold: 0.08, rootMargin: '0px 0px -40px 0px' }
  );
  revealEls.forEach(el => io.observe(el));
}

// --- Smooth scroll ---
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', function(e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth' });
    }
  });
});

// --- Persistent Spotify player toggle ---
const playerBar    = document.getElementById('player-bar');
const playerToggle = document.getElementById('player-toggle');
const playerEmbed  = document.getElementById('player-embed');

if (playerBar && playerToggle) {
  playerToggle.addEventListener('click', () => {
    const isOpen = playerBar.classList.toggle('is-open');
    playerToggle.setAttribute('aria-expanded', isOpen);
    if (playerEmbed) playerEmbed.setAttribute('aria-hidden', !isOpen);
  });
}
