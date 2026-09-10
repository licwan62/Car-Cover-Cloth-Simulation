/* Native layer extraction for generate_sewing_svg.py. Never saves the document. */
(function () {
    var doc = null;
    var previous = app.documents.length ? app.activeDocument : null;
    try {
        doc = app.open(new File(__SOURCE__));
        var roots = [], panels = {}, expected = {PANEL_TOP: true, PANEL_LEFT: true, PANEL_RIGHT: true};
        function findLayers(container) {
            for (var i = 0; i < container.layers.length; i++) {
                var layer = container.layers[i];
                if (layer.name === "PANEL" || layer.name === "01_PANEL") roots.push(layer);
                findLayers(layer);
            }
        }
        findLayers(doc);
        if (roots.length !== 1) throw Error("Expected exactly one PANEL (or 01_PANEL) layer; found " + roots.length);
        function children(item, callback) {
            var i;
            if (item.typename === "Layer") {
                for (i = 0; i < item.layers.length; i++) callback(item.layers[i]);
            }
            var items = item.typename === "CompoundPathItem" ? item.pathItems : item.pageItems;
            if (items) for (i = 0; i < items.length; i++) {
                if (items[i].parent === item) callback(items[i]);
            }
        }
        function collect(item, paths) {
            if (item.typename === "PathItem") {
                if (item.guides || item.clipping || !item.closed) throw Error("PANEL must contain a closed non-clipping path: " + item.name);
                paths.push(item);
            } else if (item.typename === "Layer" || item.typename === "GroupItem" || item.typename === "CompoundPathItem") {
                if (item.typename === "GroupItem" && item.clipped) throw Error("Clipped PANEL groups are unsupported");
                children(item, function (child) { collect(child, paths); });
            } else throw Error("Unsupported PANEL item: " + item.typename);
        }
        function visit(item) {
            var name = item.name || "";
            if (expected[name]) {
                if (panels[name]) throw Error("Duplicate " + name);
                var paths = [];
                collect(item, paths);
                if (paths.length !== 1) throw Error(name + " requires exactly one contour; found " + paths.length);
                panels[name] = paths[0];
            } else {
                if (name.indexOf("PANEL_") === 0) throw Error("Unexpected panel " + name);
                children(item, visit);
            }
        }
        children(roots[0], visit);
        var rect = doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect;
        var width = rect[2] - rect[0], height = rect[1] - rect[3];
        var scale = Number(doc.scaleFactor) || 1;
        function point(p) { return (p[0] - rect[0]) + "," + (rect[1] - p[1]); }
        function same(a, b) { return Math.abs(a[0]-b[0]) < 1e-8 && Math.abs(a[1]-b[1]) < 1e-8; }
        var xml = '<svg xmlns="http://www.w3.org/2000/svg" width="' + width*scale + 'pt" height="' + height*scale + 'pt" viewBox="0 0 ' + width + ' ' + height + '">';
        var names = ["PANEL_TOP", "PANEL_LEFT", "PANEL_RIGHT"];
        for (var k = 0; k < names.length; k++) {
            var name = names[k], path = panels[name];
            if (!path) throw Error("Missing " + name + " under PANEL");
            var points = path.pathPoints;
            if (points.length < 3) throw Error("Degenerate " + name);
            var data = "M" + point(points[0].anchor);
            for (var j = 0; j < points.length; j++) {
                var a = points[j], b = points[(j+1)%points.length];
                if (same(a.anchor, a.rightDirection) && same(b.anchor, b.leftDirection)) data += " L" + point(b.anchor);
                else data += " C" + point(a.rightDirection) + " " + point(b.leftDirection) + " " + point(b.anchor);
            }
            xml += '<path id="' + name + '" d="' + data + ' Z"/>';
        }
        xml += '</svg>';
        var output = new File(__OUTPUT__);
        output.encoding = "UTF-8";
        if (!output.open("w")) throw Error("Cannot write PANEL extraction");
        output.write(xml);
        output.close();
        return "OK";
    } catch (error) {
        return "ERROR: " + error.message;
    } finally {
        if (doc) doc.close(SaveOptions.DONOTSAVECHANGES);
        if (previous) previous.activate();
    }
})();
