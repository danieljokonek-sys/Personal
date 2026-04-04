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

// --- Services accordion ---
document.querySelectorAll('.svc-head').forEach(btn => {
  btn.addEventListener('click', () => {
    const item = btn.closest('.svc-item');
    const isOpen = item.classList.contains('is-open');
    // Close all
    document.querySelectorAll('.svc-item').forEach(i => {
      i.classList.remove('is-open');
      i.querySelector('.svc-head').setAttribute('aria-expanded', 'false');
    });
    // Open clicked (unless it was already open)
    if (!isOpen) {
      item.classList.add('is-open');
      btn.setAttribute('aria-expanded', 'true');
    }
  });
});

// --- Video lightbox modal ---
const vidModal       = document.getElementById('vid-modal');
const vidModalIframe = document.getElementById('vid-modal-iframe');
const vidModalClose  = document.getElementById('vid-modal-close');
const vidBackdrop    = document.getElementById('vid-modal-backdrop');

function openVidModal(videoId) {
  if (!vidModal || !vidModalIframe) return;
  vidModalIframe.src = `https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0`;
  vidModal.classList.add('is-open');
  vidModal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeVidModal() {
  if (!vidModal || !vidModalIframe) return;
  vidModal.classList.remove('is-open');
  vidModal.setAttribute('aria-hidden', 'true');
  vidModalIframe.src = '';
  document.body.style.overflow = '';
}

document.querySelectorAll('.work-item[data-vid]').forEach(item => {
  item.addEventListener('click', () => openVidModal(item.dataset.vid));
  item.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openVidModal(item.dataset.vid);
    }
  });
});

if (vidModalClose) vidModalClose.addEventListener('click', closeVidModal);
if (vidBackdrop)   vidBackdrop.addEventListener('click', closeVidModal);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && vidModal?.classList.contains('is-open')) closeVidModal();
});

// --- Random image glitch loop ---
(function() {
  const heroBg   = document.getElementById('hero-bg-img');
  const heroBgWrap = heroBg?.closest('.hero-bg');
  const workItems = Array.from(document.querySelectorAll('.work-item[data-vid]'));

  function glitchRandom() {
    // Pool: hero bg + all video thumbnails
    const pool = [];
    if (heroBg) pool.push({ el: heroBg, wrap: heroBgWrap, cls: 'is-glitching', wrapCls: 'is-glitching-wrap' });
    workItems.forEach(item => pool.push({ el: item, cls: 'is-glitching' }));

    if (!pool.length) return;

    const target = pool[Math.floor(Math.random() * pool.length)];
    target.el.classList.add(target.cls);
    if (target.wrap && target.wrapCls) target.wrap.classList.add(target.wrapCls);

    // Clean up after animation
    setTimeout(() => {
      target.el.classList.remove(target.cls);
      if (target.wrap && target.wrapCls) target.wrap.classList.remove(target.wrapCls);
    }, 600);

    // Schedule next glitch at random 1.2–2.8s interval
    setTimeout(glitchRandom, 1200 + Math.random() * 1600);
  }

  // First glitch after a short delay
  setTimeout(glitchRandom, 800 + Math.random() * 800);
})();

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
