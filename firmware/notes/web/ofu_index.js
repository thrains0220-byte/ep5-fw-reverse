var series = {
  control : $('#series'),

  init : function() {
    this.reset();
    this.control.on('change', this.onChange);

    model.init();
  },

  reset : function() {
    $('select', series.control).prop("selectedIndex", 0);
    info.hide();
  },

  onChange : function() {
    info.hide();
    model.reset();

    var selected = $(this).find(":selected").val();
    api.call('series', selected, model.show);
  }
};

var model = {
  control : $('#model'),
  data    : {},

  init : function() {
    this.control.on('change', this.onChange);

    version.init();
  },

  reset : function() {
    model.current = {};
    $('select', model.control).empty().append('<option selected disabled>Choose one</option>');

    version.reset()
  },

  show : function(models) {
    $.each(models, function (i, m) {
      $('select', model.control).append($('<option>', {value: m.id, text: m.name}));
    });

    model.control.css('visibility', 'visible');
  },

  onChange : function() {
    version.reset();

    var selected = $(this).find(":selected").val();
    api.call('model', selected, model.changed);
  },

  changed : function(response) {
    model.data = response;
    version.show();
  }
};

var version = {
  control  : $('#version'),
  current  : {},
  selected : '',

  init : function() {
    this.control.on('change', this.onChange);

    download.init();
  },

  reset : function() {
    version.current = {};
    $('select', version.control).empty();
    version.control.css('visibility', 'hidden');

    download.reset();
  },

  show : function() {
    $.each(model.data, function (i, m) {
      $('select', version.control).append($('<option>', {value: i, text: m.version}));
    });

    version.control.css('visibility', 'visible');
    version.control.trigger('change')

    download.show();
  },

  onChange : function() {
    version.selected = $(this).find(":selected").val();
    version.current  = model.data[version.selected];
    info.showModel();
  }
};

var download = {
  control : $('#download'),
  iframe  : $('#dliframe'),

  init : function() {
    this.control.on('click', this.onClick);
  },

  reset : function() {
    download.iframe.attr('src', '');
    download.control.css('visibility', 'hidden');
  },

  show : function() {
    download.control.css('visibility', 'visible');
  },

  onClick : function() {
    api.call('dlinfo', version.selected, download.clicked);
  },

  clicked : function(response) {
    download.iframe.attr('src', response.url);
  }
};

var api = {
  call : function(name, value, fn) {
    return $.getJSON(`api.php?${name}=${value}`, function(response){
      fn(response.data);
    })
    .fail(function(j,s,e){
      var result = (j?.responseJSON? j.responseJSON : result)
      info.show('ERROR: ' + result.msg);
    });
  }
};

var info = {
  showModel : function() {
    var fwinfo = ((version.current.date != '')? ` | Released ${version.current.date}` : '')
               + ((version.current.info != '')? ` | <a href="${version.current.info}" target="_blank">Changelog</a>` : '')

    info.show(`${version.current.category} ${version.current.name} | Firmware version ${version.current.version}${fwinfo}`)
    info.updateFileText()
  },

  updateFileText : function() {
    $('#cardfile').html(` <strong>${version.current.dlfile}</strong> renamed to <strong>${version.current.cardfile}</strong>`)
  },

  show : function (text) {
    $('#dlinfo').html(text).slideDown();
  },

  hide : function() {
    $('#dlinfo').slideUp();
  }
};


$(document).ready(function() {
  series.init();

  $('#dl button').on('click', function() {
    var model  = $('#model').find(":selected").val();
    var result = { result: false, msg: "error", data: [] };

    showModelInfo();

    $.getJSON(`api.php?download=${model}`, function(json){
      $('#cardfile').text(json.data.cardfile);
      $('#dliframe').attr('src', json.data.url);
    })
    .fail(function(j,s,e){
      result = (j?.responseJSON? j.responseJSON : result)
      showDetails('ERROR: ' + result.msg);
    })

    return false;
  });
})
