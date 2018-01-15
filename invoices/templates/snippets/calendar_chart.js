var dataTable = new google.visualization.DataTable();
dataTable.addColumn({ type: "date", id: "Date" });
dataTable.addColumn({ type: "number", id: "{{ number_header }}" });
dataTable.addColumn({ type: "string", role: "tooltip", "p": {"html": true} });

dataTable.addRows([
  {% for entry in entries %}[new Date({{ entry.0 }}, {{ entry.1 }}, {{ entry.2 }}), {{ entry.3|floatformat:2 }}, "<div style='padding:5px 5px 5px 5px;'><h4>{{ entry.4 }}</h4></div>"], {% endfor %}
]);
var chart = new google.visualization.Calendar(document.getElementById("{{ destination_id }}"));
var options = {
  title: "{{ title }}",
  height: {% if calendar_height %}{{ calendar_height }}{% else %}350{% endif %},
  tooltip: {isHtml: true}
};

chart.draw(dataTable, options);
