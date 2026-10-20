% QPM НБУ (розширена командою) у MATLAB + IRIS: фільтр, усі сценарії, графік.
% Перед запуском:  python matlab/export_inputs.py   (з кореня репозиторію)
% Запуск у MATLAB: cd matlab; run_check
% Результати: matlab/outputs/filter_matlab.csv, forecast<k>_matlab.csv, scenarios_matlab.png
% Порівняння з Python:  python matlab/compare_with_matlab.py
close all; clear; clc;
[~,~,~] = mkdir('outputs');

%% Model (the same model file as in Python)
m = Model.fromFile('../model/model.model', 'linear', true);
m = assign(m, param_check());
m = solve(m);
m = sstate(m);

%% Data prepared by Python (seasonally adjusted, nowcasts, tunes)
dq = databank.fromCSV('inputs/dq_python.csv');
r = strtrim(splitlines(fileread('inputs/ranges.txt')));
firsthist = str2q(r{1}); lasthist = str2q(r{2}); lastfore = str2q(r{3});
rngfilt = firsthist:lastfore;
rnghist = firsthist:lasthist;
rngfcast = (lasthist + 1):lastfore;

%% Filter (as a03_run_filter.m)
mult = struct();
mult.std_res_l_gdp_tnd = Series(rngfilt, 0);
mult.std_res_l_gdp_tnd(qq(2022,1):qq(2022,2)) = 0.75;
[~, filtdb] = filter(m, dq, rngfilt, 'deviation', false, 'std', mult, 'relative', true);
databank.toCSV(filtdb.mean, 'outputs/filter_matlab.csv');

%% Scenarios (as a04_run_forecast.m, plans exported from Python)
names = strtrim(splitlines(strtrim(fileread('inputs/scenarios.txt'))));
res = cell(numel(names), 1);
for k = 1:numel(names)
    initdb = dbclip(filtdb, rnghist);
    simplan = plan(m, rngfcast);
    exo = readtable(sprintf('inputs/plan%d_exo.csv', k), 'TextType', 'string');
    for i = 1:height(exo)
        per = str2q(exo.period(i)); v = char(exo.var(i));
        simplan = exogenize(simplan, v, per);
        initdb.mean.(v)(per) = exo.value(i);
    end
    endo = readtable(sprintf('inputs/plan%d_endo.csv', k), 'TextType', 'string');
    for i = 1:height(endo)
        simplan = endogenize(simplan, char(endo.shock(i)), str2q(endo.period(i)));
    end
    sh = readtable(sprintf('inputs/plan%d_shocks.csv', k), 'TextType', 'string');
    for i = 1:height(sh)
        initdb.mean.(char(sh.shock(i)))(str2q(sh.period(i))) = sh.value(i);
    end
    j = jforecast(m, initdb, rngfcast, 'plan', simplan, 'anticipate', true);
    res{k} = dbextend(initdb.mean, j.mean);
    databank.toCSV(j.mean, sprintf('outputs/forecast%d_matlab.csv', k));
end

%% Figure: scenarios computed in MATLAB/IRIS (team palette)
pal = [42 120 214; 235 104 52; 27 175 122; 237 161 0; 232 123 164] / 255;
rngp = qq(2024,3):lastfore;
% numeric time axis (decimal years) so that ticks can be plain years
t = 2024.5 + (0:numel(rngp) - 1) / 4;
nh = numel(rngp(1):lasthist);                 % history points on the plot
vars = {'d4l_cpi', 'ir_pol', 'l_er', 'l_gdp_gap'};
titles = {'Інфляція (ІСЦ), % р/р', 'Облікова ставка, %', 'Курс, грн/€', 'Розрив ВВП, % потенціалу'};
fig = figure('Color', 'w', 'Position', [100 100 1500 420], 'Visible', 'off');
tl = tiledlayout(1, 4, 'TileSpacing', 'compact', 'Padding', 'compact');
for v = 1:4
    ax = nexttile; hold(ax, 'on');
    h = gobjects(numel(names) + 1, 1);
    for k = numel(names):-1:1
        x = res{k}.(vars{v})(rngp);
        if strcmp(vars{v}, 'l_er'), x = exp(x/100); end
        if strcmp(vars{v}, 'd4l_cpi'), x = 100*(exp(x/100) - 1); end   % 100*log difference -> % y/y, as in the deck
        x(1:nh-1) = NaN;
        h(k + 1) = plot(t, x, 'LineWidth', 2, 'Color', pal(k, :));
    end
    x = res{1}.(vars{v})(rngp);
    if strcmp(vars{v}, 'l_er'), x = exp(x/100); end
    if strcmp(vars{v}, 'd4l_cpi'), x = 100*(exp(x/100) - 1); end
    x(nh+1:end) = NaN;
    h(1) = plot(t, x, 'LineWidth', 2, 'Color', [0.11 0.14 0.15]);
    yl = ylim(ax);
    p = patch(ax, [t(nh) + 0.125, t(end) + 0.125, t(end) + 0.125, t(nh) + 0.125], [yl(1) yl(1) yl(2) yl(2)], ...
        [0.94 0.94 0.93], 'EdgeColor', 'none');
    uistack(p, 'bottom'); ylim(ax, yl); xlim(ax, [t(1), t(end) + 0.125]);
    if strcmp(vars{v}, 'd4l_cpi'), yline(5, 'Color', [0.32 0.32 0.31]); end
    if strcmp(vars{v}, 'l_gdp_gap'), yline(0, 'Color', [0.32 0.32 0.31]); end
    title(titles{v}, 'FontWeight', 'bold', 'FontSize', 11); grid on; box off;
    set(ax, 'FontName', 'Segoe UI', 'GridColor', [0.88 0.88 0.85], 'GridAlpha', 1, 'Layer', 'top', ...
        'XTick', 2025:floor(t(end)), 'XTickLabel', string(2025:floor(t(end))));
    if v == 1
        lg = legend(h, ['Факт / оцінка'; names], 'Orientation', 'horizontal', 'FontSize', 9, 'Box', 'off', 'AutoUpdate', 'off');
        lg.Layout.Tile = 'south';
    end
end
title(tl, 'Сценарії, розраховані в MATLAB/IRIS (QPM НБУ, розширена командою)', 'FontSize', 12, 'FontWeight', 'bold');
exportgraphics(fig, 'outputs/scenarios_matlab.png', 'Resolution', 200);
%% Impulse responses (as b02_irfs.m): policy-rate shock for different beta; oil shock
betas = [0 0.7 1];
resp = {'l_gdp_gap', 'd4l_cpi', 'ir_pol', 'l_er', 'l_rer_gap', 'rir_pol_gap'};
rtitles = {'Розрив ВВП', 'ІСЦ, р/р', 'Облікова ставка', 'Курс грн/€ (рівень)', 'Розрив реального курсу', 'Розрив реальної ставки'};
srfs = cell(3, 1);
for b = 1:3
    mb = m; mb.beta = betas(b); mb = solve(mb); mb = sstate(mb);
    srfs{b} = srf(mb, 1:20, 'select=', {'res_ir_tlr'}, 'size', 1);
end
fig = figure('Color', 'w', 'Position', [100 100 1300 620], 'Visible', 'off');
tl = tiledlayout(2, 3, 'TileSpacing', 'compact', 'Padding', 'compact');
for v = 1:6
    ax = nexttile; hold(ax, 'on');
    for b = 1:3
        plot(0:20, srfs{b}.(resp{v}), 'LineWidth', 2, 'Color', pal(b, :));
    end
    yline(0, 'Color', [0.76 0.76 0.72]);
    title(rtitles{v}, 'FontSize', 11); grid on; box off; xlabel('квартали після шоку');
    set(ax, 'FontName', 'Segoe UI', 'GridColor', [0.88 0.88 0.85], 'GridAlpha', 1);
    if v == 1, legend({'β = 0', 'β = 0,7', 'β = 1'}, 'Location', 'best', 'Box', 'off', 'AutoUpdate', 'off'); end
end
title(tl, 'Шок облікової ставки +1 в. п. (MATLAB/IRIS)', 'FontSize', 12, 'FontWeight', 'bold');
exportgraphics(fig, 'outputs/irf_rate_matlab.png', 'Resolution', 200);

% oil: +20% real Brent price (permanent level shift through the AR(1) in its growth rate)
s_oil = 100*log(1.2)*4*(1 - 0.3);
so = srf(m, 1:16, 'select=', {'res_dl_roil'}, 'size', s_oil);
fig = figure('Color', 'w', 'Position', [100 100 1300 340], 'Visible', 'off');
tl = tiledlayout(1, 3, 'TileSpacing', 'compact', 'Padding', 'compact');
ov = {'l_roil', 'd4l_cpi', 'ir_pol'};
ot = {'Реальна ціна нафти, 100·ln від базової', 'Інфляція, р/р, в. п.', 'Облікова ставка, в. п.'};
for v = 1:3
    ax = nexttile; hold(ax, 'on');
    plot(0:16, so.(ov{v}), 'LineWidth', 2, 'Color', pal(v, :));
    if strcmp(ov{v}, 'd4l_cpi')
        plot(0:16, so.d4l_cpi_c, 'LineWidth', 2, 'Color', pal(1, :));
        legend({'Загальна', 'Базова'}, 'Location', 'northeast', 'Box', 'off', 'AutoUpdate', 'off');
    end
    yline(0, 'Color', [0.76 0.76 0.72]);
    title(ot{v}, 'FontSize', 11); grid on; box off; xlabel('квартали після шоку');
    set(ax, 'FontName', 'Segoe UI', 'GridColor', [0.88 0.88 0.85], 'GridAlpha', 1);
end
title(tl, 'Нафтовий шок: Brent +20% (MATLAB/IRIS)', 'FontSize', 12, 'FontWeight', 'bold');
exportgraphics(fig, 'outputs/irf_oil_matlab.png', 'Resolution', 200);
databank.toCSV(so, 'outputs/irf_oil_matlab.csv');

disp('Done: matlab/outputs/*');

function d = str2q(s)
    s = char(s);
    d = qq(str2double(s(1:4)), str2double(s(6)));
end
