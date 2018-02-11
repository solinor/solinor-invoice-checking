$(document).on('turbolinks:load', function () {
  $.get("/you/flexhours/json", null, function (data) {
    if (data.flex_enabled === true && "flex_hours" in data) {
      var flex_hours_count = $("#flex_hours_count");
      flex_hours_count.html(data.flex_hours.toFixed(0) + "h");
      if (data.flex_hours > 120) {
        flex_hours_count.removeClass("badge-secondary").addClass("badge-warning");
      } else if (data.flex_hours < -40) {
        flex_hours_count.removeClass("badge-secondary").addClass("badge-danger");
      }
    }
  }, "json");
});
