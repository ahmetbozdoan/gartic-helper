// Gartic.io DOM seçicileri. Site güncellenirse sadece bu dosya düzeltilmelidir.
globalThis.GarticHelper = globalThis.GarticHelper || {};

globalThis.GarticHelper.SELECTORS = Object.freeze({
  roomScreen: "#screenRoom",
  drawingContainer: "#drawing",
  drawingCanvases: "#drawing canvas",
  // Her .word bir kelime; içindeki her span bir harf, boş span = henüz açılmamış harf.
  hintWords: "#hint .word",
  answerInput: "#answer form input",
  answerMessages: "#answer .history .msg",
  // Çizen oyuncu .turn sınıfını, yerel oyuncu .you sınıfını taşır.
  drawingPlayerNick: "#users .user.turn .nick",
  localPlayerDrawing: "#users .user.you.turn",
  timer: "#time",
  // Sıra gelince çıkan iki kelimelik seçim ekranı: her .word içinde kelime (span) ve "Çiz" düğmesi.
  wordChoiceButton: ".yourTurn .containerWords .word button",
});
