$(function () {
  $.get("/you/flexhours/json", null, function (data) {
    if (data.flex_enabled === true && "flex_hours" in data) {
      $("#flex_hours_count").html(data.flex_hours.toFixed(0) + "h").removeClass("label-default").addClass("label-success");
    }
  }, "json");
});
