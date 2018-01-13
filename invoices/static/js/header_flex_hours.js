$(function () {
  $.get("/your/flexhours", null, function (data) {
    if (data.flex_enabled === true && "flex_hours" in data) {
      $("#flex_hours_count").html(data.flex_hours + "h").removeClass("label-default").addClass("label-success");
    }
  }, "json");
});
