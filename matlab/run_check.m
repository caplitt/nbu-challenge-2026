% Звірка Python-порту з оригінальною QPM НБУ (MATLAB + IRIS Toolbox).
% Перед запуском:  python matlab/export_inputs.py   (з кореня репозиторію)
% Запуск у MATLAB: cd matlab; run_check
% Результати: matlab/outputs/filter_matlab.csv, forecast_matlab.csv
% Порівняння:  python matlab/compare_with_matlab.py
close all; clear; clc;
[~,~,~] = mkdir('outputs');

%% Model (the same model file as in Python)
m = Model.fromFile('../model/model.model', 'linear', true);
m = assign(m, param_check());
m = solve(m);
m = sstate(m);

%% Data prepared by Python (seasonally adjusted, nowcasts, tunes) — isolates model/filter/forecast mechanics
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

%% Forecast with the same plan as Python (as a04_run_forecast.m)
initdb = dbclip(filtdb, rnghist);
simplan = plan(m, rngfcast);
exo = readtable('inputs/plan_exogenized.csv', 'TextType', 'string');
for k = 1:height(exo)
    per = str2q(exo.period(k));
    v = char(exo.var(k)); s = char(exo.shock(k));
    simplan = exogenize(simplan, v, per);
    simplan = endogenize(simplan, s, per);
    initdb.mean.(v)(per) = exo.value(k);
end
sh = readtable('inputs/plan_shocks.csv', 'TextType', 'string');
for k = 1:height(sh)
    s = char(sh.shock(k));
    initdb.mean.(s)(str2q(sh.period(k))) = sh.value(k);
end
j = jforecast(m, initdb, rngfcast, 'plan', simplan, 'anticipate', true);
databank.toCSV(j.mean, 'outputs/forecast_matlab.csv');
disp('Done: matlab/outputs/*.csv');

function d = str2q(s)
    s = char(s);
    d = qq(str2double(s(1:4)), str2double(s(6)));
end
