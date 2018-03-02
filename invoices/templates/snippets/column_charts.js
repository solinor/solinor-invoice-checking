  {% for barchart in column_charts %}
  var data = google.visualization.arrayToDataTable({{ barchart.2|safe }});
  var options = {
   title: "{{ barchart.1 }}",
   height: 400,
   legend: {
     position: "none",
   },
   vAxis: {
     minValue: 0,
   }
  };
  var chart = new google.visualization.ColumnChart(document.getElementById("{{ barchart.0 }}"));
  chart.draw(data, options);
  {% endfor %}
