/* =========================================================================
   EFFECTS.JS  —  Efectos de fondo (partículas y corazones flotantes)
   -------------------------------------------------------------------------
   Dibuja un canvas discreto de fondo con partículas suaves y corazones
   que flotan muy sutilmente. Diseñado para ser ligero y elegante.
   ========================================================================= */

(function () {
  const canvas = document.getElementById("bg-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  let W, H, DPR;
  let particles = [];
  let hearts = [];
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function rand(a, b) {
    // Aleatorio simple (no usamos Math.random en workflows, pero aquí en el
    // navegador es perfectamente válido).
    return a + Math.random() * (b - a);
  }

  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = W * DPR;
    canvas.height = H * DPR;
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }

  function initParticles() {
    const count = Math.round((W * H) / 26000); // densidad según pantalla
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: rand(0, W),
        y: rand(0, H),
        r: rand(0.6, 2.2),
        vx: rand(-0.15, 0.15),
        vy: rand(-0.25, -0.05),
        a: rand(0.15, 0.6),
        hue: Math.random() < 0.5 ? "255, 214, 224" : "255, 236, 200"
      });
    }
  }

  function spawnHeart() {
    hearts.push({
      x: rand(0, W),
      y: H + 30,
      size: rand(10, 22),
      speed: rand(0.25, 0.7),
      sway: rand(0.4, 1.2),
      phase: rand(0, Math.PI * 2),
      a: rand(0.05, 0.18),
      color: Math.random() < 0.5 ? "255,120,150" : "255,170,190"
    });
  }

  function drawHeart(x, y, size, color, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "rgba(" + color + ")";
    ctx.beginPath();
    const s = size / 16;
    ctx.moveTo(x, y + 4 * s);
    ctx.bezierCurveTo(x, y, x - 8 * s, y - 2 * s, x - 8 * s, y + 4 * s);
    ctx.bezierCurveTo(x - 8 * s, y + 9 * s, x, y + 12 * s, x, y + 15 * s);
    ctx.bezierCurveTo(x, y + 12 * s, x + 8 * s, y + 9 * s, x + 8 * s, y + 4 * s);
    ctx.bezierCurveTo(x + 8 * s, y - 2 * s, x, y, x, y + 4 * s);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  let heartTimer = 0;

  function frame() {
    ctx.clearRect(0, 0, W, H);

    // Partículas / luces suaves
    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.y < -10) { p.y = H + 10; p.x = rand(0, W); }
      if (p.x < -10) p.x = W + 10;
      if (p.x > W + 10) p.x = -10;

      ctx.beginPath();
      const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
      g.addColorStop(0, "rgba(" + p.hue + "," + p.a + ")");
      g.addColorStop(1, "rgba(" + p.hue + ",0)");
      ctx.fillStyle = g;
      ctx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Corazones muy discretos
    heartTimer++;
    if (heartTimer > 90 && hearts.length < 14) { spawnHeart(); heartTimer = 0; }
    for (let i = hearts.length - 1; i >= 0; i--) {
      const h = hearts[i];
      h.y -= h.speed;
      h.phase += 0.01;
      const x = h.x + Math.sin(h.phase) * h.sway * 6;
      drawHeart(x, h.y, h.size, h.color, h.a);
      if (h.y < -40) hearts.splice(i, 1);
    }

    requestAnimationFrame(frame);
  }

  function start() {
    resize();
    initParticles();
    if (!prefersReduced) requestAnimationFrame(frame);
    else {
      // Versión estática y calmada para quien prefiere menos movimiento.
      for (const p of particles) {
        ctx.beginPath();
        ctx.fillStyle = "rgba(" + p.hue + ",0.3)";
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  window.addEventListener("resize", () => { resize(); initParticles(); });
  start();
})();
