/* =========================================================================
   DATA.JS  —  CONTENIDO POR DEFECTO (fácil de editar)
   -------------------------------------------------------------------------
   Aquí puedes cambiar textos, fechas y frases directamente.
   Las FOTOS se suben normalmente desde el PANEL DE ADMIN (admin.html),
   pero también puedes poner una ruta a un archivo, por ejemplo:
      photo: "assets/photos/mi-foto.jpg"
   o una URL de internet:
      photo: "https://..."
   -------------------------------------------------------------------------
   Nota: el panel de admin guarda los cambios en el navegador. Si editas
   este archivo a mano y quieres ver los cambios, entra en el panel y pulsa
   "Restablecer a valores por defecto" (o borra los datos guardados).
   ========================================================================= */

const DEFAULT_DATA = {

  /* ---------- AJUSTES GENERALES ---------- */
  settings: {
    // Nombre de la pareja (opcional, se muestra en algunos sitios)
    coupleNames: "",

    // Texto grande de la pantalla de bienvenida
    welcomeText: "Para la persona más importante de mi vida ❤️",

    // Texto del botón de bienvenida
    welcomeButton: "Abrir nuestra historia",

    // Fecha en la que empezasteis juntos (para el contador).
    // Formato: "AAAA-MM-DDTHH:MM:SS"
    startDate: "2023-08-01T20:00:00",

    // Música de fondo. Puedes:
    //  - Subir un MP3 desde el panel de admin, o
    //  - Poner una ruta:  "assets/music/cancion.mp3"
    music: "",
    musicTitle: "Nuestra canción",
  },

  /* ---------- ❤️ NUESTRA HISTORIA (línea del tiempo) ---------- */
  timeline: [
    {
      date: "1 de Agosto, 2023",
      title: "El día que todo empezó",
      description: "El momento en el que nuestras vidas se cruzaron para siempre. No sabía que ese día cambiaría todo.",
      photo: ""
    },
    {
      date: "Septiembre, 2023",
      title: "Nuestra primera cita",
      description: "Nervios, risas y una conexión imposible de explicar. Supe que quería más días como ese.",
      photo: ""
    },
    {
      date: "Diciembre, 2023",
      title: "Nuestro primer viaje",
      description: "Descubriendo el mundo contigo. Cada lugar es más bonito cuando estás a mi lado.",
      photo: ""
    },
    {
      date: "Hoy",
      title: "Y esto no ha hecho más que empezar",
      description: "Cada día a tu lado es mi lugar favorito. Gracias por tanto.",
      photo: ""
    }
  ],

  /* ---------- 📸 GALERÍA ---------- */
  // Cada elemento: { photo, caption }
  gallery: [
    // Sube las fotos desde el panel de admin ✨
  ],

  /* ---------- 💌 CARTAS DE AMOR ---------- */
  letters: [
    {
      title: "Para ti",
      message: "Desde que llegaste, todo tiene más color. Gracias por ser mi calma y mi aventura al mismo tiempo. Te amo más de lo que las palabras pueden decir."
    },
    {
      title: "Cuando lo necesites",
      message: "Si algún día te sientes triste, vuelve a leer esto: eres increíble, eres fuerte, y yo estoy aquí para ti, hoy y siempre."
    },
    {
      title: "Un secreto",
      message: "Pienso en ti mucho más de lo que imaginas. En lo pequeño, en lo grande, en todo. Eres mi pensamiento favorito."
    }
  ],

  /* ---------- 🌹 RAZONES POR LAS QUE TE AMO (tarjetas) ---------- */
  reasons: [
    "Tu sonrisa",
    "Tu forma de cuidarme",
    "Cómo me haces sentir",
    "Porque eres mi hogar",
    "Porque contigo todo es mejor",
    "Tu mirada",
    "Tu manera de reír",
    "Porque me entiendes sin hablar"
  ],

  /* ---------- ✨ NUESTROS RECUERDOS (scrapbook) ---------- */
  // Cada elemento: { photo, note }
  scrapbook: [
    { photo: "", note: "Aquel día que no paramos de reír 🥰" },
    { photo: "", note: "Nuestro rincón favorito 🌿" },
    { photo: "", note: "Contigo hasta lo simple es especial ✨" }
  ],

  /* ---------- 🎁 CAJA SORPRESA ---------- */
  surpriseMessage: "Abrir esta caja es como abrir mi corazón: dentro solo hay una cosa… y eres tú. Gracias por existir. ❤️",

  /* ---------- 💖 100 RAZONES PARA AMARTE ---------- */
  // Puedes añadir o quitar las que quieras.
  hundredReasons: [
    "Porque tu sonrisa me alegra el día.",
    "Porque me haces sentir en casa.",
    "Porque eres valiente.",
    "Porque cuidas de los demás.",
    "Porque tus abrazos lo curan todo.",
    "Porque eres mi mejor amiga.",
    "Porque me haces reír como nadie.",
    "Porque tu mirada me desarma.",
    "Porque luchas por lo que amas.",
    "Porque eres auténtica.",
    "Porque me apoyas siempre.",
    "Porque contigo el tiempo vuela.",
    "Porque eres mi lugar seguro.",
    "Porque tu voz me calma.",
    "Porque eres detallista.",
    "Porque me inspiras a ser mejor.",
    "Porque eres fuerte y dulce a la vez.",
    "Porque bailas aunque no haya música.",
    "Porque tu forma de ver la vida me encanta.",
    "Porque eres mi persona favorita.",
    "Porque me escuchas de verdad.",
    "Porque tienes un corazón enorme.",
    "Porque me haces sentir amado.",
    "Porque eres paciente conmigo.",
    "Porque tus 'te quiero' son sinceros.",
    "Porque me tomas de la mano.",
    "Porque hueles increíble.",
    "Porque eres mi paz.",
    "Porque juntos somos mejores.",
    "Porque me eliges cada día."
  ],

  /* ---------- 🌌 CIELO ESTRELLADO ---------- */
  // Cada estrella muestra una frase al pulsarla.
  stars: [
    "Eres mi estrella favorita 🌟",
    "Contigo hasta la noche brilla.",
    "Pediría el mismo deseo mil veces: tú.",
    "Nuestro amor es infinito como el cielo.",
    "Cada estrella es un momento contigo.",
    "Te elegiría en todos los universos.",
    "Mi lugar favorito es a tu lado.",
    "Eres la luz que ilumina mis noches.",
    "Gracias por brillar en mi vida.",
    "Te amo más allá de las estrellas."
  ],

  /* ---------- 💬 MENSAJE FINAL ---------- */
  finalMessage:
    "Gracias por hacerme la persona más feliz del mundo.\n" +
    "Te elegiría una y mil veces más.\n" +
    "Te amo infinitamente ❤️"
};

// No tocar: hace que los datos estén disponibles para el resto de la web.
if (typeof window !== "undefined") window.DEFAULT_DATA = DEFAULT_DATA;
