$(document).on('turbolinks:load', function() {
  $("[data-toggle='tooltip']").tooltip();
  if (typeof pageJs === "function") {
    pageJs();
  }
});
