  {% for linechart in line_charts %}
  var data = google.visualization.arrayToDataTable({{ linechart.2|safe }});
  var options = {
   title: "{{ linechart.1 }}",
   curveType: "function",
   height: 400,
   legend: {
     position: "none",
   }
  };
  var chart = new google.visualization.LineChart(document.getElementById("{{ linechart.0 }}"));
  chart.draw(data, options);
  {% endfor %}
